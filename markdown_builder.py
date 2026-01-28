from file_loader import Article


def _format_value(value) -> str:
    if value is None or value == "":
        return "-"
    return str(value)


def build_research_markdown(article: Article, analysis: dict, primary: dict) -> str:
    keywords = ", ".join(article.keywords) if article.keywords else "-"

    lines = []
    lines.append("# Article Metadata")
    lines.append(f"- Title: {_format_value(article.title)}")
    lines.append(f"- Original Title: {_format_value(article.original_title)}")
    lines.append(f"- Original Language: {_format_value(article.original_language)}")
    lines.append(f"- Date: {_format_value(article.date_time)}")
    lines.append(f"- Source Name: {_format_value(article.source_name)}")
    lines.append(f"- Source URL: {_format_value(article.source_url)}")
    lines.append(f"- Source URL Base: {_format_value(article.source_url_base)}")
    lines.append(f"- Profile: {_format_value(article.profile_name)}")
    lines.append(f"- Keywords: {keywords}")
    lines.append("")

    lines.append("## English Translation (Full)")
    lines.append(_format_value(analysis.get("english_translation_full")))
    lines.append("")

    lines.append("## Summary")
    lines.append(_format_value(analysis.get("english_summary")))
    lines.append("")

    lines.append("## Core Topic & Original Artifact")
    lines.append(f"- Core Topic: {_format_value(analysis.get('core_topic'))}")
    lines.append(f"- Original Artifact Type: {_format_value(analysis.get('original_artifact_type'))}")
    lines.append(f"- Probable Primary Publisher: {_format_value(analysis.get('probable_primary_publisher'))}")
    lines.append(f"- Artifact Description: {_format_value(analysis.get('artifact_description'))}")
    lines.append("")

    lines.append("## Key Claims (LLM-ready bullets)")
    key_claims = analysis.get("key_claims") or []
    if key_claims:
        for claim in key_claims:
            lines.append(f"- {claim}")
    else:
        lines.append("- -")
    lines.append("")

    primary_source = primary.get("primary_source", {}) if primary else {}
    lines.append("## Primary Source")
    lines.append(f"- URL: {_format_value(primary_source.get('url'))}")
    lines.append(f"- Title: {_format_value(primary_source.get('title'))}")
    lines.append(f"- Publisher Guess: {_format_value(primary_source.get('publisher_guess'))}")
    lines.append(f"- Type Guess: {_format_value(primary_source.get('type_guess'))}")
    lines.append(f"- Confidence: {_format_value(primary_source.get('confidence'))}")
    lines.append("")

    lines.append("## Alternative Sources")
    alternatives = primary.get("alternatives", []) if primary else []
    if alternatives:
        for alt in alternatives:
            lines.append(
                "- {url} | {title} | {reason} | confidence: {confidence}".format(
                    url=_format_value(alt.get("url")),
                    title=_format_value(alt.get("title")),
                    reason=_format_value(alt.get("reason")),
                    confidence=_format_value(alt.get("confidence")),
                )
            )
    else:
        lines.append("- -")
    lines.append("")

    lines.append("## LLM Article Brief")
    lines.append("Context:")
    lines.append(_format_value(analysis.get("english_summary")))
    lines.append("")
    lines.append("What happened:")
    lines.append(_format_value(analysis.get("core_topic")))
    lines.append("")
    lines.append("Why it matters:")
    lines.append(_format_value(analysis.get("artifact_description")))
    lines.append("")
    lines.append("Key data points:")
    if key_claims:
        for claim in key_claims:
            lines.append(f"- {claim}")
    else:
        lines.append("- -")
    lines.append("")
    lines.append("Suggested angle(s) for a news story:")
    lines.append("- Focus on the primary source and explain the original artifact and its implications.")

    return "\n".join(lines)
