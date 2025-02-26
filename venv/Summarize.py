import os

import Keys
from openai import OpenAI

# Initialize OpenAI API client (replace with your actual API key or ensure environment variable is set)
api_key = os.environ.get("OPENAI_API_KEY", Keys.OPENAI_API)
client = OpenAI(api_key=api_key)  # Using OpenAI client as recommended in the latest OpenAI SDK&#8203;:contentReference[oaicite:3]{index=3}

# Directory to monitor
MONITOR_DIR = r"C:\Users\User\Dropbox\Current\2025"

def list_recent_files(directory, count=10):
    """Retrieve the most recent files (by creation time) in the directory (including subfolders)."""
    all_files = []
    for root, dirs, files in os.walk(directory):
        for fname in files:
            full_path = os.path.join(root, fname)
            all_files.append(full_path)
    if not all_files:
        return []
    # Sort files by creation time (newest first)
    all_files.sort(key=lambda f: os.path.getctime(f), reverse=True)
    recent_files = all_files[:count]
    print("\nRecent files:")
    for idx, file_path in enumerate(recent_files):
        print(f"  {idx}: {file_path}")
    return recent_files

# Start monitoring/interaction loop
print(f"Monitoring directory: {MONITOR_DIR}")
print("Press 'r' to list the 10 most recent files, or enter a file ID to summarize it, or 'q' to quit.")
recent_files = []  # will hold the last listed files for reference

while True:
    command = input("\nEnter command (r = refresh, q = quit, or file ID): ").strip().lower()
    if command == 'q':
        print("Exiting program.")
        break
    elif command == 'r':
        # Refresh and list recent files
        try:
            recent_files = list_recent_files(MONITOR_DIR, count=10)
            if not recent_files:
                print("No files found in the directory yet.")
        except Exception as e:
            print(f"Error while scanning directory: {e}")
            continue
    else:
        # The user might be attempting to select a file by ID
        if command == '':
            continue  # empty input, ignore
        if not recent_files:
            print("No files have been listed yet. Press 'r' to refresh the file list.")
            continue
        # Check if the command is a valid number
        try:
            file_index = int(command)
        except ValueError:
            print("Invalid input. Please enter 'r', 'q', or a number corresponding to a listed file.")
            continue
        if file_index < 0 or file_index >= len(recent_files):
            print("Invalid file ID. Please choose a number from the listed range.")
            continue

        selected_file = recent_files[file_index]
        # Double-check the file exists
        if not os.path.isfile(selected_file):
            print("Selected file not found (it may have been moved or deleted).")
            continue
        # Only proceed if it's a PDF file (skip if not PDF)
        if not selected_file.lower().endswith(".pdf"):
            print("The selected file is not a PDF. Please choose a PDF file to summarize.")
            continue

        print(f"\nExtracting text from: {selected_file}")
        text_content = ""
        try:
            # Attempt PDF text extraction
            from PyPDF2 import PdfReader
            reader = PdfReader(selected_file)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:  # if extract_text returned something
                    text_content += page_text
        except Exception as e:
            print(f"Error: Could not extract text from the PDF ({e}).")
            continue

        if not text_content.strip():
            print("No extractable text found in the PDF file. Skipping summarization.")
            continue

        # Prepare prompt for summarization (you can adjust the system/user messages as needed)
        prompt_message = (
            "Summarize in bullet points very succinctly, focus on the opinions not the data:\n" + text_content
        )
        messages = [
            {"role": "system", "content": "You are a hedge fund analyst"},
            {"role": "user", "content": prompt_message}
        ]

        print("Sending content to OpenAI API for summarization...")
        summary = ""
        try:
            # Create a chat completion (summary) using the GPT-4o model
            completion = client.chat.completions.create(
                model="gpt-4o",
                messages=messages
            )
            # Extract the summary text from the response
            summary = completion.choices[0].message.content.strip()
        except Exception as api_err:
            print(f"OpenAI API request failed: {api_err}")
            # (You could add retry logic or specific exception handling here)
            continue

        # Output the summary with the file name as the title
        file_name = os.path.basename(selected_file)
        print(f"\n### S{file_name} ###")
        print(summary)
        print("\n" + "#" * 50 + "\n")  # separator line after the summary for readability
