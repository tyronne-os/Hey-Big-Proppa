import os

os.environ["BOO_HARVEST"] = "0"      # tests must never fire the real BETTER-VERSE collection triggers or touch the network
os.environ.pop("HF_TOKEN", None)
os.environ.pop("HUGGINGFACE_TOKEN", None)
