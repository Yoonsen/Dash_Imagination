import argparse
import subprocess
import os
from datetime import datetime

def run_command(command, description):
    print(f"\n=== {description} ===")
    try:
        result = subprocess.run(command, shell=True, check=True, text=True, capture_output=True)
        print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error during {description}:")
        print(e.stderr)
        return False

def build_and_deploy(app_path, project_id, app_name, rebuild=False):
    # Construct the full image name
    image_name = f"gcr.io/{project_id}/{app_name}:latest"
    
    # Ensure we're in the correct directory
    os.chdir(app_path)
    
    # Build Docker image
    build_command = f"docker build -t {image_name} ."
    if not run_command(build_command, "Building Docker image"):
        return False

    # Push to Container Registry
    push_command = f"docker push {image_name}"
    if not run_command(push_command, "Pushing to Container Registry"):
        return False

    # Deploy to Cloud Run (using your existing YAML)
    deploy_command = "gcloud builds submit --config cloudbuild.deploy.yaml"
    if not run_command(deploy_command, "Deploying to Cloud Run"):
        return False

    return True

def main():
    parser = argparse.ArgumentParser(description='Build and deploy app to Cloud Run')
    parser.add_argument('--app-path', required=True, help='Path to the application directory')
    parser.add_argument('--project-id', required=True, help='Google Cloud project ID')
    parser.add_argument('--app-name', required=True, help='Application name')
    parser.add_argument('--rebuild', action='store_true', help='Force a complete rebuild')
    
    args = parser.parse_args()

    # Start time for logging
    start_time = datetime.now()
    print(f"Starting build and deploy process at {start_time}")

    success = build_and_deploy(
        app_path=args.app_path,
        project_id=args.project_id,
        app_name=args.app_name,
        rebuild=args.rebuild
    )

    # End time and duration
    end_time = datetime.now()
    duration = end_time - start_time
    
    print(f"\nProcess {'completed successfully' if success else 'failed'}")
    print(f"Duration: {duration}")

if __name__ == "__main__":
    main()