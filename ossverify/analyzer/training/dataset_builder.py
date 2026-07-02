import concurrent.futures
import csv
import os
from dataclasses import dataclass
from typing import Dict, List, Optional

csv.field_size_limit(10_000_000)  # repo corpus text fields can exceed the 131072-char default

from ossverify.analyzer.domain_analyzer import Domain
from ossverify.collector.github_http import GITHUB_API_BASE, GitHubHTTPClient

# GitHub repository topic tags used to label training examples per domain.
# A repo can match multiple topics across domains -> multi-label.
DOMAIN_TOPICS: Dict[Domain, List[str]] = {
    Domain.BACKEND: ["backend", "rest-api"],
    Domain.FRONTEND: ["frontend", "react", "vue"],
    Domain.AI_ML: ["machine-learning", "deep-learning"],
    Domain.DEVOPS: ["devops", "ci-cd"],
    Domain.CLOUD: ["cloud-computing", "aws"],
    Domain.SECURITY: ["cybersecurity", "penetration-testing"],
    Domain.BLOCKCHAIN: ["blockchain", "ethereum"],
}


@dataclass
class TrainingExample:
    repo_full_name: str
    text: str
    labels: List[str]


class DatasetBuilder:
    def __init__(
        self,
        github_token: Optional[str] = None,
        repos_per_topic: int = 60,
        commits_per_repo: int = 30,
        prs_per_repo: int = 30,
        max_workers: int = 10,
    ):
        self.client = GitHubHTTPClient(github_token)
        self.repos_per_topic = repos_per_topic
        self.commits_per_repo = commits_per_repo
        self.prs_per_repo = prs_per_repo
        self.max_workers = max_workers

    def _search_repos_by_topic(self, topic: str) -> List[dict]:
        results = self.client.paginate(
            f"{GITHUB_API_BASE}/search/repositories",
            {"q": f"topic:{topic}", "sort": "stars", "order": "desc"},
            items_key="items",
            max_pages=1,
        )
        return results[: self.repos_per_topic]

    def _repo_text_corpus(self, full_name: str, description: str = "") -> str:
        commits = self.client.paginate(f"{GITHUB_API_BASE}/repos/{full_name}/commits", {}, max_pages=1)
        commit_text = " ".join(c["commit"]["message"] for c in commits[: self.commits_per_repo])

        prs = self.client.paginate(f"{GITHUB_API_BASE}/repos/{full_name}/pulls", {"state": "all"}, max_pages=1)
        pr_text = " ".join(f"{p['title']} {p.get('body') or ''}" for p in prs[: self.prs_per_repo])

        # commit/PR text is long and noisy (chores, typo fixes); description carries the clearest
        # domain signal but is short, so put it first (survives truncation) and repeat it so it
        # isn't drowned out once the tokenizer truncates to max_length.
        description_text = f"{description} {description} {description}".strip()
        return f"{description_text} {commit_text} {pr_text}".strip()

    def build(self, verbose: bool = True, checkpoint_path: Optional[str] = None) -> List[TrainingExample]:
        repo_labels: Dict[str, set] = {}
        repo_descriptions: Dict[str, str] = {}
        for domain, topics in DOMAIN_TOPICS.items():
            for topic in topics:
                repos = self._search_repos_by_topic(topic)
                for raw in repos:
                    repo_labels.setdefault(raw["full_name"], set()).add(domain.value)
                    repo_descriptions.setdefault(raw["full_name"], raw.get("description") or "")
                if verbose:
                    print(f"[search] topic={topic} domain={domain.value} repos={len(repos)} total_unique={len(repo_labels)}", flush=True)

        done: Dict[str, TrainingExample] = {}
        if checkpoint_path and os.path.exists(checkpoint_path):
            with open(checkpoint_path, encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    done[row["repo_full_name"]] = TrainingExample(
                        repo_full_name=row["repo_full_name"],
                        text=row["text"],
                        labels=row["labels"].split("|") if row["labels"] else [],
                    )
            if verbose and done:
                print(f"[resume] loaded {len(done)} existing examples from {checkpoint_path}", flush=True)

        pending = [(name, labels) for name, labels in repo_labels.items() if name not in done]
        examples = list(done.values())
        total = len(repo_labels)
        processed = len(done)

        with concurrent.futures.ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._repo_text_corpus, name, repo_descriptions.get(name, "")): (name, labels)
                for name, labels in pending
            }
            for future in concurrent.futures.as_completed(futures):
                full_name, labels = futures[future]
                try:
                    text = future.result()
                except Exception as exc:
                    text = ""
                    if verbose:
                        print(f"[corpus] error on {full_name}: {exc}", flush=True)
                processed += 1
                if text:
                    example = TrainingExample(repo_full_name=full_name, text=text, labels=sorted(labels))
                    examples.append(example)
                    if checkpoint_path:
                        self._append_checkpoint(checkpoint_path, example)
                if verbose and processed % 10 == 0:
                    print(f"[corpus] {processed}/{total} repos processed, {len(examples)} usable examples so far", flush=True)
        return examples

    @staticmethod
    def _append_checkpoint(path: str, example: TrainingExample) -> None:
        write_header = not os.path.exists(path)
        with open(path, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if write_header:
                writer.writerow(["repo_full_name", "text", "labels"])
            writer.writerow([example.repo_full_name, example.text, "|".join(example.labels)])

    @staticmethod
    def save_csv(examples: List[TrainingExample], path: str) -> None:
        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["repo_full_name", "text", "labels"])
            for example in examples:
                writer.writerow([example.repo_full_name, example.text, "|".join(example.labels)])


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()
    builder = DatasetBuilder(github_token=os.getenv("GITHUB_TOKEN"))
    output_path = os.path.join(os.path.dirname(__file__), "dataset.csv")
    examples = builder.build(checkpoint_path=output_path)
    print(f"saved {len(examples)} examples to {output_path}")
