import csv
import os
import random

csv.field_size_limit(10_000_000)  # repo corpus text fields can exceed the 131072-char default
os.environ.setdefault("USE_TF", "0")  # avoid transformers importing TensorFlow/Keras (not used here)

import torch
from torch.utils.data import Dataset
from transformers import AutoModelForSequenceClassification, AutoTokenizer, Trainer, TrainingArguments

from ossverify.analyzer.domain_analyzer import Domain

MODEL_NAME = "bert-base-uncased"
DOMAIN_LABELS = [d.value for d in Domain]
MODEL_OUTPUT_DIR = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "models", "domain_bert"))
DEFAULT_DATASET_PATH = os.path.join(os.path.dirname(__file__), "dataset.csv")


class DomainDataset(Dataset):
    def __init__(self, texts, label_vectors, tokenizer, max_length=256):
        self.encodings = tokenizer(texts, truncation=True, padding=True, max_length=max_length)
        self.labels = label_vectors

    def __len__(self):
        return len(self.labels)

    def __getitem__(self, idx):
        item = {key: torch.tensor(value[idx]) for key, value in self.encodings.items()}
        item["labels"] = torch.tensor(self.labels[idx], dtype=torch.float)
        return item


def load_dataset(csv_path):
    texts, label_vectors = [], []
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            labels = set(row["labels"].split("|")) if row["labels"] else set()
            label_vectors.append([1.0 if domain in labels else 0.0 for domain in DOMAIN_LABELS])
            texts.append(row["text"][:5000])
    return texts, label_vectors


def train(dataset_path: str = DEFAULT_DATASET_PATH, output_dir: str = MODEL_OUTPUT_DIR, epochs: int = 3, seed: int = 42):
    texts, label_vectors = load_dataset(dataset_path)

    # dataset.csv rows are grouped by the topic search order in dataset_builder.py
    # (e.g. all Blockchain repos at the end) -- shuffle before splitting so eval isn't
    # skewed toward whichever domain happened to be searched last.
    rng = random.Random(seed)
    indices = list(range(len(texts)))
    rng.shuffle(indices)
    texts = [texts[i] for i in indices]
    label_vectors = [label_vectors[i] for i in indices]

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForSequenceClassification.from_pretrained(
        MODEL_NAME, num_labels=len(DOMAIN_LABELS), problem_type="multi_label_classification"
    )

    split = max(int(len(texts) * 0.85), 1)
    train_dataset = DomainDataset(texts[:split], label_vectors[:split], tokenizer)
    eval_dataset = DomainDataset(texts[split:], label_vectors[split:], tokenizer) if texts[split:] else train_dataset

    args = TrainingArguments(
        output_dir=os.path.join(output_dir, "checkpoints"),
        num_train_epochs=epochs,
        per_device_train_batch_size=8,
        per_device_eval_batch_size=8,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        logging_steps=10,
        report_to=[],
    )

    trainer = Trainer(model=model, args=args, train_dataset=train_dataset, eval_dataset=eval_dataset)
    trainer.train()

    os.makedirs(output_dir, exist_ok=True)
    model.save_pretrained(output_dir)
    tokenizer.save_pretrained(output_dir)
    print(f"model saved to {output_dir}")


if __name__ == "__main__":
    train()
