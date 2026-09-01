import Foundation

public enum RecordingRuleMatcher {
    private static func normalize(_ string: String) -> String {
        string.trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
            .components(separatedBy: .whitespacesAndNewlines)
            .filter { !$0.isEmpty }
            .joined(separator: " ")
    }

    private static func keywordMatches(query: String?, airing: HDHomeRunGuideEntry) -> Bool {
        guard let query = query, !query.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return true
        }
        let terms = query.split(separator: ",").map { normalize(String($0)) }.filter { !$0.isEmpty }
        if terms.isEmpty { return true }
        let haystacks = [airing.episodeTitle, airing.synopsis, airing.category, airing.title]
            .compactMap { $0 }
            .map { normalize($0) }
        return terms.contains { term in
            haystacks.contains { $0.contains(term) }
        }
    }

    private static func titleMatches(ruleTitle: String, airingTitle: String?, mode: String?) -> Bool {
        guard let airingTitle = airingTitle, !airingTitle.isEmpty else { return false }
        let normRule = normalize(ruleTitle)
        let normAiring = normalize(airingTitle)
        if mode == "contains" {
            return normAiring.contains(normRule)
        }
        return normRule == normAiring
    }

    public static func findMatchingRule(
        rules: [HDHomeRunRecordingRule],
        channelNumber: String?,
        airing: HDHomeRunGuideEntry?
    ) -> HDHomeRunRecordingRule? {
        guard let airing = airing else { return nil }

        // 1. Episode rule exact match (DateTimeOnly == airing.start)
        if let start = airing.start {
            if let match = rules.first(where: { rule in
                guard let dt = rule.dateTimeOnly else { return false }
                let timeMatches = abs(dt - start) < 60
                if let ruleCh = rule.channelOnly, let ch = channelNumber {
                    let channels = ruleCh.split(separator: "|").map { String($0) }
                    return timeMatches && channels.contains(ch)
                }
                return timeMatches && (rule.seriesId == airing.seriesId || rule.title.caseInsensitiveCompare(airing.title) == .orderedSame)
            }) {
                return match
            }
        }

        // 2. Series / Title / Keyword rules
        return rules.first(where: { rule in
            guard rule.isSeriesRule else { return false }
            if let ruleCh = rule.channelOnly, let ch = channelNumber {
                let channels = ruleCh.split(separator: "|").map { String($0) }
                if !channels.contains(ch) { return false }
            }
            let seriesMatches = !rule.seriesId.isEmpty && !(airing.seriesId ?? "").isEmpty && rule.seriesId == airing.seriesId
            let titleMatchesAiring = titleMatches(ruleTitle: rule.title, airingTitle: airing.title, mode: rule.titleMatchMode)
            if !seriesMatches && !titleMatchesAiring { return false }
            return keywordMatches(query: rule.keywordQuery, airing: airing)
        })
    }
}
