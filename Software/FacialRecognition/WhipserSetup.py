import os
import whisper
import torch

def setup_whisper_model():
    print("Setting up Whisper small model...")

    # Create the models directory if it doesn't exist
    models_dir = os.path.join(os.path.dirname(__file__), "models")
    os.makedirs(models_dir, exist_ok=True)

    # Path to the cached model file
    model_path = os.path.join(models_dir, "small.pt")

    # Check if the GPU is available
    device = "cuda" if torch.cuda.is_available() else "cpu"

    # Check if the cached model file exists
    if os.path.exists(model_path):
        print("Small model already cached, loading from local file.")
        # Load the model from the cached file
        model = whisper.load_model("small", device=device, in_file=model_path)
    else:
        # Check if the GPU is available
        if device:
            print(f"Downloading and caching small model using {device} device.")
            # Download and cache the small model on the GPU
            model = whisper.load_model("small", device=device)
            torch.save(model.state_dict(), model_path)
            print("Small model cached successfully.")
        else:
            print("GPU is not available, skipping small model download.")
            return None

    return model

if __name__ == "__main__":
    setup_whisper_model()