"""
Script to generate the canonical submission.jsonl file for the 30 test pairs.
Follows challenge-brief.md §7.2 contract.
"""

import json
from pathlib import Path
from bot import compose

EXPANDED_DIR = Path(__file__).parent / "dataset" / "expanded"
TEST_PAIRS_FILE = EXPANDED_DIR / "test_pairs.json"
SUBMISSION_FILE = Path(__file__).parent / "submission.jsonl"


def load_json(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def main():
    if not TEST_PAIRS_FILE.exists():
        print(f"Error: {TEST_PAIRS_FILE} does not exist. Run generate_dataset.py first.")
        return

    test_pairs_data = load_json(TEST_PAIRS_FILE)
    pairs = test_pairs_data.get("pairs", [])
    print(f"Loaded {len(pairs)} test pairs.")

    categories = {}
    cat_dir = EXPANDED_DIR / "categories"
    for f in cat_dir.glob("*.json"):
        data = load_json(f)
        categories[data.get("slug", f.stem)] = data

    results = []
    for pair in pairs:
        test_id = pair["test_id"]
        trigger_id = pair["trigger_id"]
        merchant_id = pair["merchant_id"]
        customer_id = pair.get("customer_id")

        trg_file = EXPANDED_DIR / "triggers" / f"{trigger_id}.json"
        mer_file = EXPANDED_DIR / "merchants" / f"{merchant_id}.json"

        if not (trg_file.exists() and mer_file.exists()):
            print(f"Skipping {test_id}: missing file {trg_file} or {mer_file}")
            continue

        trigger = load_json(trg_file)
        merchant = load_json(mer_file)

        cat_slug = merchant.get("category_slug", "dentists")
        category = categories.get(cat_slug, {"slug": cat_slug})

        customer = None
        if customer_id:
            cust_file = EXPANDED_DIR / "customers" / f"{customer_id}.json"
            if cust_file.exists():
                customer = load_json(cust_file)

        print(f"Composing for {test_id} ({cat_slug} / {trigger.get('kind')})...")
        composed = compose(category, merchant, trigger, customer)

        line = {
            "test_id": test_id,
            "trigger_id": trigger_id,
            "merchant_id": merchant_id,
            "customer_id": customer_id,
            "body": composed["body"],
            "cta": composed.get("cta", "binary_yes_no"),
            "send_as": composed.get("send_as", "vera"),
            "suppression_key": composed.get("suppression_key", trigger.get("suppression_key", "")),
            "rationale": composed.get("rationale", "")
        }
        results.append(line)

    with open(SUBMISSION_FILE, "w", encoding="utf-8") as f:
        for item in results:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"Successfully generated {len(results)} lines in {SUBMISSION_FILE}")


if __name__ == "__main__":
    main()
