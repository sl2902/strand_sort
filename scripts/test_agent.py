# test_agent.py
import json
from strand_sort.agent.intake_agent import run_intake_workflow

if __name__ == "__main__":
    # Test with local image folder
    sample_images = ["data/raw/confectionery/snickers_1.png", "data/raw/confectionery/snickers_2.png"]
    print("--- RUNNING STRANDS AGENT INTAKE WORKFLOW ---")
    result = run_intake_workflow(sample_images)
    print(result)