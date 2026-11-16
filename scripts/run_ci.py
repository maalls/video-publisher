"""Run the selected CI mode without logging credentials."""
import os
import subprocess
from video_publisher.ci import ci_arguments


def main():
    args = ci_arguments(
        os.environ.get("GITHUB_EVENT_NAME", ""),
        os.environ.get("INPUT_MODE", ""),
        os.environ["RUN_DATE"],
        os.environ.get("ENABLE_DAILY") == "true",
        os.environ.get("ENABLE_YOUTUBE") == "true",
    )
    child_env = os.environ.copy()
    # Choosing private-test is explicit upload consent for this manual run only.
    # It does not change repository variables or enable the daily job.
    child_env["ENABLE_YOUTUBE"] = str("--publish-youtube" in args).lower()
    subprocess.run(["video-publisher", *args], env=child_env, check=True)


if __name__ == "__main__":
    main()
