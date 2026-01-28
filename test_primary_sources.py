#!/usr/bin/env python3
"""
Test primary source finding on specific articles.
"""

import json
import sys
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from config import load_config
from file_loader import load_article
from primary_source_finder import find_primary_source
from translation_analysis import translate_and_analyse_article
from primary_source_resolver import PrimarySourceResolver
from llm_clients import LLMError


def test_article(article_path: str, config: dict):
    """Test primary source finding for a single article."""
    print("\n" + "=" * 100)
    print(f"ARTICLE: {Path(article_path).name}")
    print("=" * 100)
    
    try:
        # Load article
        article = load_article(article_path)
        print(f"\nTitle: {article.title[:80]}...")
        print(f"Original URL: {article.source_url}")
        
        # Translation & Analysis
        print("\n[1/3] Running translation & analysis...")
        analysis = translate_and_analyse_article(article, "gemini-2.5-pro", config)
        print(f"  ✓ Language: {analysis.get('language_detected', 'N/A')}")
        print(f"  ✓ Topic: {analysis.get('core_topic', 'N/A')[:60]}...")
        print(f"  ✓ Artifact type: {analysis.get('original_artifact_type', 'N/A')}")
        print(f"  ✓ Publisher guess: {analysis.get('probable_primary_publisher', 'N/A')}")
        
        # Primary Source Finding
        print("\n[2/3] Searching for primary source...")
        try:
            primary = find_primary_source(article, analysis, config)
            primary_source = primary.get("primary_source", {})
            
            if primary_source.get('url'):
                print(f"  ✓ Found URL: {primary_source.get('url')}")
                print(f"  - Title: {primary_source.get('title', 'N/A')[:60]}...")
                print(f"  - Confidence: {primary_source.get('confidence', 0):.2f}")
                print(f"  - Type: {primary_source.get('type_guess', 'N/A')}")
            else:
                print(f"  ✗ No primary source URL found")
                print(f"  - Reasoning: {primary.get('reasoning_summary', 'N/A')[:100]}...")
        
        except LLMError as e:
            print(f"  ✗ Primary source search failed: {e}")
            primary = {
                "primary_source": {"url": None, "confidence": 0.0},
                "reasoning_summary": f"Failed: {e}"
            }
        
        # Validation
        print("\n[3/3] Validating primary source...")
        resolver = PrimarySourceResolver(config)
        article_payload = article.to_dict()
        article_payload["_filename"] = Path(article_path).name
        article_payload["_file_path"] = str(article_path)
        
        resolution = resolver.resolve(primary, article_payload)
        
        if resolution.resolved_url:
            print(f"  ✓ VALIDATED: {resolution.resolved_url}")
            print(f"\n  → This URL will be used in the article")
            return resolution.resolved_url
        else:
            print(f"  ✗ Validation failed - no valid URL")
            if resolution.report.get('candidates_tried'):
                print(f"  - Tried {len(resolution.report['candidates_tried'])} candidates")
                for attempt in resolution.report['candidates_tried'][:3]:
                    print(f"    • {attempt.get('original_url')} -> {attempt.get('reason')}")
            print(f"\n  → Article will be published WITHOUT a primary source link")
            return None
            
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return None


def main():
    """Test primary source finding on three specified articles."""
    base_dir = Path("/Users/m4owen/Library/CloudStorage/GoogleDrive-gunn0r@gmail.com/Shared drives/01.Player Clothing Team Drive/02. RetroShell/13. Articles and Data/09. Feed Finder/barcelona_news/2026-01/15/7am Scrape/01. Priority - Barcelona & Catalonia")
    
    # Find the actual files (they may have slightly different names due to special characters)
    articles = []
    for pattern in ["01-*.json", "02-*.json", "03-*.json"]:
        matches = list(base_dir.glob(pattern))
        if matches:
            articles.append(matches[0])
        else:
            print(f"Warning: No file matching {pattern}")
    
    if not articles:
        print("Error: No articles found!")
        sys.exit(1)
    
    print("\n" + "=" * 100)
    print("PRIMARY SOURCE TESTING - 3 ARTICLES")
    print("=" * 100)
    
    # Load config
    config = load_config()
    if not config.get("GEMINI_API_KEY"):
        print("\n✗ GEMINI_API_KEY required")
        sys.exit(1)
    
    results = {}
    
    for article_path in articles:
        if not article_path.exists():
            print(f"\n✗ File not found: {article_path.name}")
            results[article_path.name] = "FILE_NOT_FOUND"
            continue
        
        url = test_article(str(article_path), config)
        results[article_path.name] = url or "NO_PRIMARY_SOURCE"
    
    # Summary
    print("\n\n" + "=" * 100)
    print("SUMMARY - PRIMARY SOURCE URLS")
    print("=" * 100)
    
    for i, (filename, url) in enumerate(results.items(), 1):
        print(f"\n{i}. {filename[:70]}...")
        if url == "FILE_NOT_FOUND":
            print(f"   ✗ File not found")
        elif url == "NO_PRIMARY_SOURCE":
            print(f"   ✗ No valid primary source found")
        else:
            print(f"   ✓ {url}")
    
    print("\n" + "=" * 100)


if __name__ == "__main__":
    main()
