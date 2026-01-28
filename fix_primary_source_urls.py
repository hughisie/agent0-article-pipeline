"""Script to validate and fix incorrect primary source URLs in registry."""
import json
from pathlib import Path

from primary_source_validator import validate_primary_source_url
from url_validator import validate_url


def validate_registry_urls():
    """Validate all URLs in the primary sources registry."""
    registry_path = Path("primary_sources_registry.json")

    if not registry_path.exists():
        print("Registry not found")
        return

    with open(registry_path, 'r', encoding='utf-8') as f:
        registry = json.load(f)

    print(f"Checking {len(registry)} registry entries...\n")

    invalid_entries = []
    warning_entries = []

    for idx, entry in enumerate(registry, 1):
        url = entry.get('url')
        if not url:
            continue

        print(f"[{idx}/{len(registry)}] Checking: {url}")

        # Basic URL validation
        result = validate_url(url, timeout=10, retries=1)

        if not result.ok:
            invalid_entries.append({
                'url': url,
                'reason': result.reason,
                'status': result.status_code,
                'article_ids': entry.get('article_ids', [])
            })
            print(f"  ✗ INVALID: {result.reason}")
        elif result.status_code != 200:
            warning_entries.append({
                'url': url,
                'status': result.status_code,
                'final_url': result.final_url
            })
            print(f"  ⚠ WARNING: Status {result.status_code}")
        else:
            print(f"  ✓ OK")

    # Summary
    print(f"\n{'='*60}")
    print(f"Validation complete!")
    print(f"Total: {len(registry)}")
    print(f"Valid: {len(registry) - len(invalid_entries) - len(warning_entries)}")
    print(f"Warnings: {len(warning_entries)}")
    print(f"Invalid: {len(invalid_entries)}")

    # Show invalid entries
    if invalid_entries:
        print(f"\n{'='*60}")
        print("INVALID URLs (should be removed):")
        print(f"{'='*60}")
        for entry in invalid_entries:
            print(f"\nURL: {entry['url']}")
            print(f"Reason: {entry['reason']}")
            print(f"Status: {entry['status']}")
            print(f"Used in articles: {entry['article_ids']}")

    # Show warnings
    if warning_entries:
        print(f"\n{'='*60}")
        print("WARNING URLs (may need review):")
        print(f"{'='*60}")
        for entry in warning_entries:
            print(f"\nURL: {entry['url']}")
            print(f"Status: {entry['status']}")
            if entry['final_url'] != entry['url']:
                print(f"Redirects to: {entry['final_url']}")

    # Offer to clean registry
    if invalid_entries:
        print(f"\n{'='*60}")
        response = input(f"\nRemove {len(invalid_entries)} invalid URLs from registry? (yes/no): ").strip().lower()
        if response == 'yes':
            # Filter out invalid URLs
            invalid_urls = {entry['url'] for entry in invalid_entries}
            cleaned_registry = [e for e in registry if e.get('url') not in invalid_urls]

            # Backup original
            backup_path = registry_path.with_suffix('.json.backup')
            with open(backup_path, 'w', encoding='utf-8') as f:
                json.dump(registry, f, indent=2, ensure_ascii=False)
            print(f"✓ Backup saved: {backup_path}")

            # Save cleaned registry
            with open(registry_path, 'w', encoding='utf-8') as f:
                json.dump(cleaned_registry, f, indent=2, ensure_ascii=False)
            print(f"✓ Cleaned registry saved: {len(cleaned_registry)} entries")
            print(f"✓ Removed: {len(registry) - len(cleaned_registry)} invalid URLs")


if __name__ == '__main__':
    validate_registry_urls()
