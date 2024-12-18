// Function to start the report generation process
function startReportGeneration() {
    const progressContainer = document.getElementById("progress-container");
    const progressBar = document.getElementById("progress-bar");
    const progressText = document.getElementById("progress-text");
    const generateButton = document.getElementById("generate-report-button");
    const regenerateButton = document.getElementById("regenerate-report-button");
    const reportFrame = document.getElementById("report-frame");

    // Hide the Generate Report button and Regenerate button
    if (generateButton) generateButton.style.display = "none";
    if (regenerateButton) regenerateButton.style.display = "none";

    // Reset UI: Clear iframe, reset progress bar and text
    reportFrame.src = ""; // Clear the iframe content
    progressBar.style.width = "0%";
    progressText.innerText = "Starting process...";

    // Show progress bar and progress text
    progressContainer.style.display = "block";
    progressText.style.display = "block";

    // Trigger the backend to start report generation
    fetch('/generate_report/', { method: 'POST' })
        .then(response => {
            if (!response.ok) {
                throw new Error("Error starting report generation");
            }
            // Start polling for progress
            let progressInterval = setInterval(() => {
                fetch('/progress/')
                    .then(response => response.json())
                    .then(progress => {
                        console.log("Received progress:", progress); // Debugging log
                        updateProgress(progress);

                        // Stop polling when progress reaches 100%
                        if (progress.percent === 100) {
                            clearInterval(progressInterval);
                        }
                    })
                    .catch(err => {
                        console.error("Error fetching progress:", err);
                        clearInterval(progressInterval);
                    });
            }, 1000); // Poll every second
        })
        .catch(err => {
            console.error(err);
            progressText.innerText = "Error during report generation.";
        });
}    
    
//    OLD fetch("/generate_report/", { method: "POST" })
//        .then(() => {
//            // Start polling for progress updates
//            updateProgress();
//        })
//        .catch((error) => console.error("Error starting report generation:", error));
//}

// Function to update progress and handle UI changes
function updateProgress(progress) {
    console.log("Updating progress UI with:", progress); // Debugging log
    const progressBar = document.getElementById("progress-bar");
    const progressText = document.getElementById("progress-text");

            if (progress.percent < 100) {
                progressBar.style.width = `${progress.percent}%`;
                progressText.textContent = `${progress.stage} ${progress.company} (${progress.percent}%)`;
            } else {
                // When progress is 100, load the report and show the "Regenerate Report" button
                progressBar.style.width = "100%";
                progressText.innerText = "Report generation complete!";
                reportFrame.src = "/view-report/";
                progressContainer.style.display = "none";
                progressText.style.display = "none";
                regenerateButton.style.display = "block";
            }
}
