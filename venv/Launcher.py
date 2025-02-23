import subprocess
import sys

# List your script names here.
scripts = [ 'publisher.py', 'discord_mt.py', 'WSBSENTIMENT CHECK.py', 'publisher_v2.py','FLYBOTY.py', 'Newsfeeder.py']

# Start all scripts concurrently.
processes = [subprocess.Popen([sys.executable, script]) for script in scripts]

# Wait for all processes to finish.
for process in processes:
    process.wait()

print("All scripts have been executed concurrently.")
