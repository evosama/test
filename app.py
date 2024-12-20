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
ninja_org_ids = []
ninja_org_report = []
devices_ages_and_companies = []
ninja_licenced = 0
ninja_unlicensed = 0
bd_licensed = 0 
bd_unlicensed = 0
bd_org_report = []

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")

templates = Jinja2Templates(directory="templates")

# Global progress tracking
progress = {"percent": 0, "stage": "", "company": ""}

# Update progress function
def update_progress(progress_value):
    global progress
    progress = progress_value

#Ninja API and Functions Block
# Retrieves the access token required for authentication with the NinjaRMM API.
def get_access_token():
    token_url = "https://app.ninjarmm.com/oauth/token"
    client_id = 'clientIDPlaceholder'
    client_secret = 'clientSecretPlaceholder'
    data = {'grant_type': 'client_credentials', 'redirect_uri': 'https://localhost', 'scope': 'monitoring'}
    response = requests.post(token_url, data=data, verify=True, allow_redirects=False, auth=(client_id, client_secret))
    tokens = json.loads(response.text)
    return tokens['access_token']

# Connects to the NinjaRMM API to retrieve and store organization IDs and names.
def connect_to_ninja(update_progress_callback=None):
    access_token = get_access_token()
    api_url = "https://app.ninjarmm.com/api/v2/organizations"
    headers = {'Authorization': f'Bearer {access_token}'}
    response = requests.get(api_url, headers=headers, verify=True).json()
    
    if isinstance(response, list):
        for idx, org in enumerate(response):
            company_name = org.get("name")
            ninja_org_ids.append({"company_name": company_name, "company_id": org.get("id")})
            
            # Update progress for Ninja organizations
            if update_progress_callback:
                update_progress_callback("Gathering data from Ninja for", company_name, idx + 1, len(response))
    elif isinstance(response, dict):
        for idx, org in enumerate(response.get("items", [])):
            company_name = org.get("name")
            ninja_org_ids.append({"company_name": company_name, "company_id": org.get("id")})
            
            # Update progress for Ninja organizations
            if update_progress_callback:
                update_progress_callback("Gathering data from Ninja for", company_name, idx + 1, len(response.get("items", [])))
    else:
        print("Unexpected response format:", response)


# Retrieves device counts for each organization and categorizes them.
# :param org: Organization data dictionary with keys 'company_name' and 'company_id'
def get_devices_from_orgs(org):
    access_token = get_access_token()
    api_url = f"https://app.ninjarmm.com/api/v2/organization/{org['company_id']}/devices"
    headers = {'Authorization': f'Bearer {access_token}'}
    response = requests.get(api_url, headers=headers, verify=True).json()
    
    device_counts = {
        "Number of Servers": 0,
        "Number of Workstations": 0,
        "Number of Clouds": 0,
        "Number of VM Hosts": 0,
        "Number of VM Guests": 0,
    }

    # If additional node categories are required, find them in the NinjaOne API.
    for device in response:
        node_class = device["nodeClass"]
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
    
    device_report = {"company_name": org["company_name"], **device_counts}
    ninja_org_report.append(device_report)

# Checks the age of devices in each organization and records devices not updated in over 90 days.
# :param org_id: Organization ID for which devices' ages are to be checked
def age_of_devices_per_org(org_id):
    access_token = get_access_token()
    api_url = f"https://app.ninjarmm.com/api/v2/organization/{org_id}/devices"
    headers = {'Authorization': f'Bearer {access_token}'}
    response = requests.get(api_url, headers=headers, verify=True).json()
    
    # If the response is a list, iterate directly
    if isinstance(response, list):
        for device in response:
            if device.get('nodeClass') in ['WINDOWS_WORKSTATION', 'MAC']:
                last_update = device.get('lastUpdate')
                if last_update:
                    last_update_time = datetime.datetime.fromtimestamp(last_update)
                    current_time = datetime.datetime.today()
                    days_since_update = (current_time - last_update_time).days
                    
                    if days_since_update >= 90:
                        devices_ages_and_companies.append({
                            'Company': device.get('organizationId'),
                            'device_name': device.get('systemName')
                        })
    else:
        print(f"Unexpected response format for org_id {org_id}: {response}")    

#Bitdefender API and Functions Block 
# Functions to connect in a session with Bitdefender.
def create_authorization_header(api_key):
    login_string = f"{api_key}:"
    encoded_bytes = base64.b64encode(login_string.encode())
    return "Basic " + encoded_bytes.decode()

def make_request(session, url, method, params):
    headers = {
        "Content-Type": "application/json",
        "Authorization": create_authorization_header("authorizationHeaderPlaceholder")
    }
    request_data = json.dumps({
        "jsonrpc": "2.0",
        "method": method,
        "params": params,
        "id": "idPlaceholder"
    })
    return session.post(url, data=request_data, verify=True, headers=headers).json()

def connect_to_bitdefender():
    api_endpoint_url = "https://cloud.gravityzone.bitdefender.com/api/v1.0/jsonrpc/network"
    params = {"filters": {"companyType": 1, "licenseType": 3}}
    return make_request(requests.Session(), api_endpoint_url, "getCompaniesList", params)

# Functions to retrieve the counts for managed devices, active licences, and expired licenses.
def get_managed_equipment_count(session, company_id):
    api_endpoint_url = "https://cloud.gravityzone.bitdefender.com/api/v1.0/jsonrpc/Network"
    params = {"parentId": company_id, "perPage": 100}
    response = make_request(session, api_endpoint_url, "getEndpointsList", params)
    return [item['id'] for item in response['result']['items'] if item['isManaged']]

def get_licensed_status(session, endpoint_id):
    api_endpoint_url = "https://cloud.gravityzone.bitdefender.com/api/v1.0/jsonrpc/Network"
    params = {"endpointId": endpoint_id}
    response = make_request(session, api_endpoint_url, "getManagedEndpointDetails", params)
    return response['result']['agent']['licensed']

# Function to categorize the counts and display the progress of processing in the terminal for the user.
def process_companies(companies, update_progress_callback=None):
    global bd_licensed, bd_unlicensed
    session = requests.Session()

    for idx, company in enumerate(companies):
        managed_equipment = get_managed_equipment_count(session, company['id'])
        bd_licensed = sum(get_licensed_status(session, equip_id) == 1 for equip_id in managed_equipment)
        bd_unlicensed = sum(get_licensed_status(session, equip_id) == 2 for equip_id in managed_equipment)

        # Appends the information we need to a json file.
        bd_org_report.append({
            "Company_Name": company['name'],
            "Managed": len(managed_equipment),
            "Licensed": bd_licensed,
            "Expired_License": bd_unlicensed
        })

        # Update progress for Bitdefender organizations
        if update_progress_callback:
            update_progress_callback("Gathering data from Bitdefender for", company['name'], idx + 1, len(companies))

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
    global progress

    # Progress callback function
    def update_progress(stage, company, current, total):
        progress["stage"] = stage
        progress["company"] = company
        progress["percent"] = int((current / total) * 100)
        print(f"Progress Update: {progress}")  # Debugging line

    try:
        # Reset progress
        progress = {"stage": "Starting process...", "company": "", "percent": 0}

        # Step 1: Connect to NinjaRMM and fetch organization data
        connect_to_ninja(update_progress_callback=update_progress)
        total_orgs = len(ninja_org_ids)
        if total_orgs == 0:
            raise Exception("No organizations found in NinjaRMM.")
        # Process NinjaRMM organizations (updates handled in `connect_to_ninja`)
        for i, org in enumerate(ninja_org_ids):
            get_devices_from_orgs(org)  # Fetch device counts
            age_of_devices_per_org(org["company_id"])  # Check device ages
            update_progress("Processing devices for", org["company_name"], i + 1, total_orgs)

        # Step 2: Connect to Bitdefender and process company data
        bitdefender_companies = connect_to_bitdefender()
        total_companies = len(bitdefender_companies.get("result", []))
        if total_companies == 0:
            raise Exception("No companies found in Bitdefender.")
        # Process Bitdefender companies (updates handled in `process_companies`)
        for i, company in enumerate(bitdefender_companies["result"]):
            process_companies([company], update_progress_callback=update_progress)
            update_progress("Processing data for", company["name"], i + 1, total_companies)

        # Step 3: Generate the HTML report
        progress["stage"] = "Generating report..."
        progress["company"] = ""
        progress["percent"] = 90
        generate_full_report()
        progress["percent"] = 100
        progress["stage"] = "Completed"

    except Exception as e:
        # Handle any errors gracefully
        progress["stage"] = "Error"
        progress["company"] = ""
        progress["percent"] = 100
        print(f"An error occurred: {e}")

# Route for the main page
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# Endpoint to trigger the process in the background
@app.post("/generate_report/")
async def generate_report(background_tasks: BackgroundTasks):
    global progress
    background_tasks.add_task(run_script, background_tasks)
    return {"message": "Report generation started"}

# Endpoint to get progress updates
@app.get("/progress/")
async def get_progress():
    global progress
    print(f"Progress Endpoint Called: {progress}")  # Debugging line
    return progress

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
