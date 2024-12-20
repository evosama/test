// Function to start the report generation process
function startReportGeneration() {
    const progressBar = document.getElementById("progress-bar");
    const progressText = document.getElementById("progress-text");
    const generateButton = document.getElementById("generate-report-button");
    const regenerateButton = document.getElementById("regenerate-report-button");
    const reportFrame = document.getElementById("report-frame");

    // Reset and display progress elements
    progressBar.parentElement.style.display = "block";
    progressText.style.display = "block";
    progressBar.style.width = "0%";
    progressText.innerText = "Starting process...";
    generateButton.disabled = true;
    regenerateButton.style.display = "none";
    reportFrame.src = ""; // Clear previous report

    // Trigger backend report generation
    fetch('/generate_report/', { method: 'POST' })
        .then(response => {
            if (!response.ok) {
                throw new Error("Error starting report generation.");
            }
            // Start polling for progress
            const progressInterval = setInterval(() => {
                fetch('/progress/')
                    .then(response => response.json())
                    .then(data => {
                        if (data.percent < 100) {
                            progressBar.style.width = `${data.percent}%`;
                            progressText.innerText = `${data.stage} ${data.company} (${data.percent}%)`;
                        } else {
                            clearInterval(progressInterval);
                            progressBar.parentElement.style.display = "none";
                            generateButton.style.display = "none";
                            progressText.innerText = "Report generation complete!";
                            regenerateButton.style.display = "block";
                            reportFrame.src = '/view-report/';
                        }
                    })
                    .catch(error => {
                        console.error("Error fetching progress:", error);
                        clearInterval(progressInterval);
                        progressText.innerText = "Error during report generation.";
                        generateButton.disabled = false;
                    });
            }, 1000); // Poll every second
        })
        .catch(error => {
            console.error("Error initiating report generation:", error);
            progressText.innerText = "Error during report generation.";
            generateButton.disabled = false;
        });
}
