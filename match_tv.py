from matching.tv_matcher import TVMatcher


def main() -> None:
    matcher = TVMatcher()
    matches = matcher.find_candidates(min_score=50)
    print(f"[MATCH] candidates={len(matches)}")

    for item, event, tv in matcher.candidate_details(matches):
        print(
            f"[MATCH] score={item.score} status={item.status} "
            f"event={event['name']!r} event_start={event['start_datetime']} | "
            f"tv_channel={tv['channel']!r} tv_title={tv['title']!r} "
            f"tv_start={tv['start_datetime']} | reasons={','.join(item.reasons)}"
        )


if __name__ == "__main__":
    main()
