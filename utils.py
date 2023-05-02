import glob 
import torch
from nanoChatGPT.model import GPTLanguageModel
from nanoChatGPT.config import learning_rate, device,LARGE_GPT_CONFIG, SMALL_GPT_CONFIG, KOGPT_CONFIG, LLAMA_7B_CONFIG
from pathlib import Path
import numpy as np
import random

# Save the model.
def save_model(epoch: int, model, optimizer, PATH: str) -> None:
    model_state_dict = {
        "model": model.state_dict(),
        "optimizer": optimizer.state_dict(),
        "epoch": epoch
    }   

    # assert PATH[-1] == "/", "Please check the save directory."
    save_dir = Path(PATH) / f"epoch-{epoch}.tar"
    torch.save(model_state_dict, str(save_dir))

# Load the last training checkpoint result.
def get_last_epoch(PATH: str) -> int:
    """Get the last epoch and TAR file"""
    path = Path(PATH)
    files = glob.glob(f"{str(path)}/*")
    if len(files) == 0:
        return None
    
    epochs = [int(filename.split("/")[-1].split(".")[0].split("-")[-1]) for filename in files]
    return max(epochs)

# Load the model with the configuration. 
def load_model(PATH, config, best=True):
    model = GPTLanguageModel(config).to(device)
    optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate, betas=(0.9, 0.95))

    if best:
        # assert PATH[-1] == "/", "Please Check the PATH Arguments"
        path = Path(PATH)
        last_epoch = get_last_epoch(str(path))
        path = path / f"epoch-{last_epoch}.tar"
        model_state_dict = torch.load(str(path))
    else:
        # assert PATH[-1] != "/", "Please Check the PATH Arguments"
        path = Path(PATH)
        assert path.exists(), "Please Check the model is existed."
        model_state_dict = torch.load(str(path))

    model.load_state_dict(model_state_dict["model"])
    optimizer.load_state_dict(model_state_dict["optimizer"])
    start_epoch = model_state_dict["epoch"]

    return model, optimizer, start_epoch


def getModelConfig(model_size):
    configs = {"small":SMALL_GPT_CONFIG, "large":LARGE_GPT_CONFIG, "KOGPT":KOGPT_CONFIG, "LLAMA": LLAMA_7B_CONFIG}
    assert model_size in configs.keys(), "Please Choose Appropriate Model Size"
    config = configs[model_size]

    return config

mean = lambda li: sum(li)/len(li)

@torch.no_grad()
def estimate_loss(model, train_loader, val_loader):
    out = {}
    model.eval()
    for split in ["train", "val"]:
        losses = []
        d = train_loader if split=="train" else val_loader

        for X, Y in d:
            _, loss = model(X, Y)
            losses.append(loss.item())

        out[split] = mean(losses)

    model.train()
    return out


def set_seed():
    seed=12499489
    torch.manual_seed(seed)
    np.random.seed(seed)
    random.seed(seed)
    torch.cuda.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.benchmark = False
    torch.backends.cudnn.deterministic = True