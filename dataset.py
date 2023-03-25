import glob
import pandas as pd
import json
import torch
from torch.utils.data import Dataset
import gzip
import numpy as np
from transformers import AutoTokenizer
from xml.etree.ElementTree import parse
from sys import getsizeof
import numpy as np
import tqdm

from config import device


def encode_from_texts(texts:list[str], tokenizer: AutoTokenizer, block_size:int):
    tokens = []
    pbar = tqdm.tqdm(
        texts,
        smoothing=0,
        leave=True,
        dynamic_ncols=True,
    )
    for text in pbar:
        # print(text
        if text == "":
            continue

        temp_tokens = np.array(tokenizer.encode(text), dtype=np.int64)
        length = len(temp_tokens)
        padding = -length % (block_size+1) 
        temp_tokens = np.reshape(np.concatenate((temp_tokens, np.zeros(padding))), (-1, block_size+1))
        # print(temp_tokens.shape)
        tokens = np.concatenate((tokens, temp_tokens), axis=0) if len(tokens) != 0 else temp_tokens

    return tokens

def read_text_from_xml(xml_dir:str):
    try:
        tree = parse(xml_dir)
        root = tree.getroot()
        text = " ".join([x.text for x in root.findall("text")[0].findall("p")])
        return text
    except: return ''

def encode_text_from_xml(folder_dir: str, tokenizer: AutoTokenizer, block_size:int):
    assert folder_dir[-1] != "/", "Check the directory please."
    xml_file_directories = glob.glob(f"{folder_dir}/*")

    texts = [read_text_from_xml(xml_dir) for xml_dir in xml_file_directories]
    
    tokens = encode_from_texts(texts, tokenizer, block_size)

    return tokens


class TokenedDataset(Dataset):
    def __init__(
            self, 
            file_path:str, 
            tokenizer:AutoTokenizer, 
            block_size:int, 
            from_cache:bool=False, 
            save_cache: bool=False, 
            cache_destination: str = "dataset_cache.tar.gz",
            device:str="cuda"
        ):
        self.device = device
        self.block_size = block_size

        if from_cache:
            open_func = gzip.open if file_path.endswith(".gz") else open

            with open_func(cache_destination, "rb") as f:
                self.tokens = np.load(f)
            self.num_subsets = self.tokens.shape[0]
            return

        self.tokens = encode_text_from_xml(file_path, tokenizer=tokenizer, block_size=block_size)
        self.num_subsets = self.tokens.shape[0]

        if save_cache:
            self.save_cache(cache_destination)

    def save_cache(self, cache_destination):
        with gzip.open(cache_destination, "wb") as f:
            np.save(f, self.tokens)

    def __len__(self):
        return self.num_subsets

    def __getitem__(self, idx):
        x = torch.as_tensor(self.tokens[idx][:-1], dtype=torch.long, device=self.device)
        y = torch.as_tensor(self.tokens[idx][1:], dtype=torch.long, device=self.device)

        return x, y

    def __repr__(self) -> str: 
        return f"TokenDataset containing {self.num_subsets} subsets."


# Data Loading Optimization
class GPTDataset(Dataset):
    def __init__(self, txt_file, tokenizer, block_size, encoding):
        self.block_size = block_size
        self.tokenizer = tokenizer
        self.encode = lambda x: self.tokenizer.encode(x, add_special_tokens=True, max_length=block_size+1, padding=True, truncation=True)        
        print(f"Loading Enormous Corpus Start...")
        with open(txt_file, "r", encoding=encoding) as f:
            self.tokens = f.read()
        print(f"Loading Corpus File Done!")

        # self.encoded_token = tokenizer.encode(self.tokens)
        self.length = len(self.tokens) // (self.block_size+1) - 4
        print(f"Dataset Size: {len(self.tokens)}")

    def __len__(self):
        return self.length

    def __getitem__(self, idx):
        start_idx = idx * self.block_size
        end_idx = (idx + 3) * self.block_size
        # tokens = self.encoded_token[start_idx:end_idx+1]
        t = self.tokens[start_idx: end_idx+1]
        tokens = self.encode(t)
        # print(tokens, len(tokens))
        x = torch.tensor(tokens[:-1]).long()
        y = torch.tensor(tokens[1:]).long()
        
        x, y = x.to(device), y.to(device)
        return x, y
    

class ParagraphDataset(torch.utils.data.Dataset):
    def __init__(self, filepath, tokenizer, block_size):
        self.filepath = filepath
        self.tokenizer = tokenizer
        self.block_size = block_size
        self.blocks = []
        self._load_blocks()

    def __len__(self):
        return len(self.blocks)

    def __getitem__(self, index):
        block = self.blocks[index]
        encoded_block = self.tokenizer.encode_plus(
            block,
            add_special_tokens=True,
            max_length=self.block_size,
            truncation=True,
            padding='max_length',
            return_attention_mask=True,
            return_tensors='pt'
        )
        return encoded_block

    def _load_blocks(self):
        with open(self.filepath, 'r', encoding='utf-8') as f:
            current_block = ""
            for line in f:
                line = line.strip()
                if len(line) == 0:
                    if len(current_block) > 0:
                        blocks = self.tokenizer.batch_encode_plus(
                            [current_block],
                            add_special_tokens=True,
                            max_length=self.block_size,
                            truncation=True,
                            padding='max_length',
                            return_attention_mask=True,
                            return_tensors='pt'
                        )['input_ids']
                        for i in range(blocks.size(1)):
                            self.blocks.append(blocks[:, i:i+self.block_size])
                        current_block = ""
                else:
                    current_block += line + " "
            if len(current_block) > 0:
                blocks = self.tokenizer.batch_encode_plus(
                    [current_block],
                    add_special_tokens=True,
                    max_length=self.block_size,
                    truncation=True,
                    padding='max_length',
                    return_attention_mask=True,
                    return_tensors='pt'
                )['input_ids']
                for i in range(blocks.size(1)):
                    self.blocks.append(blocks[:, i:i+self.block_size])



def create_dataset():
    files = glob.glob("./dataset/NIKLNEWSPAPER_2022_v1.0/*.json")
    result = ''
    for raw_data_path in files:
        with open(raw_data_path) as f:
            js = json.loads(f.read())
        df = pd.DataFrame(js["document"])

        paragraphs = df["paragraph"]
        sentences = [sentence["form"] for article in paragraphs for sentence in article ]

        result += "\n".join(sentences)

    with open("data.txt", "w") as f:
        f.writelines(result)


if __name__ == '__main__':
    # create_dataset()
    tokenizer = AutoTokenizer.from_pretrained(
    'kakaobrain/kogpt', revision='KoGPT6B-ryan1.5b-float16',
    bos_token='[BOS]', eos_token='[EOS]', unk_token='[UNK]', pad_token='[PAD]', mask_token='[MASK]'
    )
    # encode_text_from_xml("./dataset/NIKL_NP_v1.2/malmungchi", tokenizer=tokenizer, block_size=128)
        
    dataset = TokenedDataset("./dataset/NIKL_NP_v1.2/malmungchi", tokenizer=tokenizer, block_size=128, save_cache=True)
    print(dataset[0])
            
        