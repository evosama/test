from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
import time
import json
import requests
import datetime
import base64
import os

#Global variables
ninja_client_id = 'placeholder'
ninja_client_secret = 'placeholder'
ninja_org_list = []
ninja_org_report = []
devices_ages_and_companies = []
ninja_licenced = 0
ninja_unlicensed = 0
bd_api_url = "placeholder"
bd_api_key = "placeholder"
bd_client_id = "placeholder"
bd_licensed = 0 
bd_unlicensed = 0
bd_org_report = []
app = FastAPI()

progress_data = {"Stage": "", "Company": "", "Percent": 0}

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


#Ninja API and Functions Block
# Retrieves the access token required for authentication with the NinjaRMM API.
def get_access_token():
    token_url = "https://app.ninjarmm.com/oauth/token"
    data = {'grant_type': 'client_credentials', 'redirect_uri': 'https://localhost', 'scope': 'monitoring'}
    response = requests.post(token_url, data=data, verify=True, allow_redirects=False, auth=(ninja_client_id, ninja_client_secret))
    tokens = json.loads(response.text)
    return tokens['access_token']

def fetch_ninja_data():
    access_token = get_access_token()  # Retrieve access token once
    orgs_url = "https://app.ninjarmm.com/api/v2/organizations"
    headers = {'Authorization': f'Bearer {access_token}'}

    # Fetch Ninja organizations
    response = requests.get(orgs_url, headers=headers, verify=True).json()
    ninja_orgs = response if isinstance(response, list) else response.get("items", [])

    if not ninja_orgs:
        print("No organizations found.")
        return

    for org in ninja_orgs:
        ninja_org_name = org.get("name")
        ninja_org_id = org.get("id")
        ninja_org_list.append({"company_name": ninja_org_name, "company_id": ninja_org_id})

        # Fetch device counts
        devices_url = f"https://app.ninjarmm.com/api/v2/organization/{ninja_org_id}/devices"
        devices_response = requests.get(devices_url, headers=headers, verify=True).json()

        device_counts = {
            "Number of Servers": 0,
            "Number of Workstations": 0,
            "Number of Clouds": 0,
            "Number of VM Hosts": 0,
            "Number of VM Guests": 0,
        }

        # If additional node categories are required, find them in the NinjaOne API.
        for device in devices_response:
            node_class = device.get("nodeClass", "")
            if node_class in ["WINDOWS_SERVER", "MAC_SERVER", "LINUX_SERVER"]:
                device_counts["Number of Servers"] += 1
            elif node_class in ["WINDOWS_WORKSTATION", "MAC", "LINUX_WORKSTATION"]:
                device_counts["Number of Workstations"] += 1
            elif node_class == "CLOUD_MONITOR_TARGET":
                device_counts["Number of Clouds"] += 1
            elif node_class in ["VMWARE_VM_HOST", "HYPERV_VMM_HOST"]:
                device_counts["Number of VM Hosts"] += 1
            elif node_class in ["VMWARE_VM_GUEST", "HYPERV_VMM_GUEST"]:
                device_counts["Number of VM Guests"] += 1

            # Checks the age of devices in each organization and records devices not updated in over 90 days.  
            last_update = device.get("lastUpdate")
            if last_update and node_class in ["WINDOWS_WORKSTATION", "MAC"]:
                last_update_time = datetime.datetime.fromtimestamp(last_update)
                current_time = datetime.datetime.today()
                days_since_update = (current_time - last_update_time).days

                if days_since_update >= 90:
                    devices_ages_and_companies.append({
                        "Company": ninja_org_name,
                        "Device Name": device.get("systemName"),
                        "Days Since Update": days_since_update,
                    })

        # Append the report for this organization
        ninja_org_report.append({
            "company_name": ninja_org_name,
            **device_counts,
        })  

#Bitdefender API and Functions Block 

def make_request(session, url, method, params):
    def create_bd_auth_header():
        login_string = f"{bd_api_key}:"
        encoded_bytes = base64.b64encode(login_string.encode())
        return "Basic " + encoded_bytes.decode()

    headers = {
        "Content-Type": "application/json",
        "Authorization": create_bd_auth_header()
    }
    request_data = json.dumps({
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": bd_client_id
    })
    return session.post(url, data=request_data, verify=True, headers=headers).json()

#def fetch_bd_data ():
    # FIGURE OUT HOW TO CONSOLIDATE connect_to_bitdefender(RENAME TO get_bd_orglist?), get_managed_bd_device_count, get_bd_license_status, AND bd_device_counts HERE.
#    return []

def connect_to_bitdefender():
    org_params = {"filters": {"companyType": 1, "licenseType": 3}}
    return make_request(requests.Session(), bd_api_url, "getCompaniesList", org_params)

# Functions to retrieve the counts for managed devices, active licences, and expired licenses.
def get_managed_bd_device_count(session, company_id):
    device_params = {"parentId": company_id, "perPage": 100}
    device_response = make_request(session, bd_api_url, "getEndpointsList", device_params)
    return [item['id'] for item in device_response['result']['items'] if item['isManaged']]

def get_bd_license_status(session, endpoint_id):
    isLicenced_params = {"endpointId": endpoint_id}
    isLicenced_response = make_request(session, bd_api_url, "getManagedEndpointDetails", isLicenced_params)
    return isLicenced_response['result']['agent']['licensed']

# Function to categorize the counts.
def bd_device_counts(bd_orgs):
    global bd_licensed, bd_unlicensed
    session = requests.Session()

    for bd_org in enumerate(bd_orgs):
        managed_equipment = get_managed_bd_device_count(session, bd_org['id'])
        bd_licensed = sum(get_bd_license_status(session, equip_id) == 1 for equip_id in managed_equipment)
        bd_unlicensed = sum(get_bd_license_status(session, equip_id) == 2 for equip_id in managed_equipment)

        # Appends the information we need to a json file.
        bd_org_report.append({
            "Company_Name": bd_org['name'],
            "Managed": len(managed_equipment),
            "Licensed": bd_licensed,
            "Expired_License": bd_unlicensed
        })

        bd_licensed = bd_unlicensed = 0


# Sets up the HTML head, title, and styles.
def setup_html_head():
    return """
    <html>
    <head>
        <title>Monthly Device Counts Report</title>
        <!-- Link to external CSS -->
        <link rel="stylesheet" type="text/css" href="/static/css/styles.css">
    </head>
    <body>
    """

# Function to display Ninja information in HTML format
def create_ninja_html_report():
    ninja_html_content = """   
        <h1>Ninja RMM Equipment Report</h1>
        <table>
            <tr>
                <th>Company Name</th>
                <th>Number of Servers</th>
                <th>Number of Workstations</th>
                <th>Number of Clouds</th>
                <th>Number of VM Hosts</th>
                <th>Number of VM Guests</th>
            </tr>
    """
    for report in ninja_org_report:
        ninja_html_content += f"""
            <tr>
                <td>{report['company_name']}</td>
                <td>{report['Number of Servers']}</td>
                <td>{report['Number of Workstations']}</td>
                <td>{report['Number of Clouds']}</td>
                <td>{report['Number of VM Hosts']}</td>
                <td>{report['Number of VM Guests']}</td>
            </tr>
        """
    ninja_html_content += """
        </table>
    """
    return ninja_html_content

# Function to display Bitdefender information in HTML format
def create_bd_html_report ():
    bd_html_content = """
            <h1>Bitdefender Equipment Report</h1>
            <table>
                <thead>
                    <tr>
                        <th>Company Name</th>
                        <th>Managed Equipment Count</th>
                        <th>Active License Count</th>
                        <th>Expired License Count</th>
                    </tr>
                </thead>
    """
    for report in bd_org_report:
        bd_html_content += f"""
            <tr>
                <td>{report['Company_Name']}</td>
                <td>{report['Managed']}</td>
                <td>{report['Licensed']}</td>
                <td>{report['Expired_License']}</td>
            </tr>
        """
    bd_html_content += """
        </table>
    """
    return bd_html_content

def generate_full_report():
    html_head = setup_html_head()
    ninja_counts = create_ninja_html_report()
    bitdefender_counts = create_bd_html_report()
    html_content = html_head + ninja_counts + bitdefender_counts + "</body></html>"

    # Define the "reports" directory within the project's directory
    project_dir = os.path.dirname(os.path.abspath(__file__))
    reports_dir = os.path.join(project_dir, "reports")

    # Create the "reports" directory if it doesn't exist
    os.makedirs(reports_dir, exist_ok=True)

    # Generate a timestamped filename
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"MonthlyCounts_{timestamp}.html"
    filepath = os.path.join(reports_dir, filename)

    # Save the HTML content to the file
    with open(filepath, "w") as html_file:
        html_file.write(html_content)
        print(f"Report successfully saved to {filepath}!")

    return filepath  # Return the full path of the saved report

def get_most_recent_report():
    reports_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
    # Check if the directory exists and contains files
    if not os.path.exists(reports_dir) or not os.listdir(reports_dir):
        return None

    # Find the most recent file in the "reports" directory
    reports = [os.path.join(reports_dir, f) for f in os.listdir(reports_dir) if f.endswith(".html")]
    if not reports:
        return None

    latest_report = max(reports, key=os.path.getctime)  # Sort by creation time
    return latest_report

# Function that runs the script logic
async def run_script(background_tasks: BackgroundTasks):
    global progress_data

    # Progress callback function
    def update_progress(stage, company, current, total):
        progress_data["Stage"] = stage
        progress_data["Company"] = company
        progress_data["Percent"] = int((current / total) * 100)
        print(f"Progress Update: {progress_data}")  # Debugging line

    try:
        # Reset progress
        progress_data = {"Stage": "Starting process...", "Company": "", "Percent": 0}

        # Step 1: Fetch Ninja organization data and update progress bar.
        fetch_ninja_data()
        total_ninja_orgs = len(ninja_org_list)
        for i, ninja_org in enumerate(ninja_org_list):
            update_progress("Processing Ninja data for", ninja_org["company_name"], i + 1, total_ninja_orgs)

        # Step 2: Connect to Bitdefender and process company data
        bitdefender_orgs = connect_to_bitdefender()
        total_bd_orgs = len(bitdefender_orgs.get("result", []))
        if total_bd_orgs == 0:
            raise Exception("No companies found in Bitdefender.")
        # Process Bitdefender companies (updates handled in `process_companies`)
        for i, company in enumerate(bitdefender_orgs["result"]):
            bd_device_counts([company])
            update_progress("Processing Bitdefender data for", company["name"], i + 1, total_bd_orgs)

        # Step 3: Generate the HTML report
        progress_data["stage"] = "Generating report..."
        progress_data["company"] = ""
        progress_data["percent"] = 90
        generate_full_report()
        progress_data["percent"] = 100
        progress_data["stage"] = "Completed"

    except Exception as e:
        # Handle any errors gracefully
        progress_data["stage"] = "Error"
        progress_data["company"] = ""
        progress_data["percent"] = 100
        print(f"An error occurred: {e}")

# Route for the main page
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# Endpoint to trigger the process in the background
@app.post("/generate_report/")
async def generate_report(background_tasks: BackgroundTasks):
    global progress_data
    background_tasks.add_task(run_script, background_tasks)
    return {"message": "Report generation started"}

# Endpoint to get progress updates
@app.get("/progress/")
async def get_progress():
    global progress_data
    print(f"Progress Endpoint Called: {progress_data}")  # Debugging line
    return progress_data

@app.get("/view-report/", response_class=HTMLResponse)
async def view_report():
    # Get the most recent report file
    latest_report = get_most_recent_report()
    if not latest_report:
        return HTMLResponse("<h1>No reports found!</h1>", status_code=404)
    else:
    # Read and return the contents of the latest report
        with open(latest_report, "r", encoding="utf-8") as file:
            report_content = file.read()
        return HTMLResponse(content=report_content)
