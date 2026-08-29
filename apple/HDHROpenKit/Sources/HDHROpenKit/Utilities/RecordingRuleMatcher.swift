import Foundation

public enum RecordingRuleMatcher {
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
                    return timeMatches && ruleCh == ch
                }
                return timeMatches && (rule.seriesId == airing.seriesId || rule.title.caseInsensitiveCompare(airing.title) == .orderedSame)
            }) {
                return match
            }
        }

        // 2. Series rule match
        if let seriesId = airing.seriesId, !seriesId.isEmpty {
            if let match = rules.first(where: { rule in
                rule.isSeriesRule && rule.seriesId == seriesId && (rule.channelOnly == nil || rule.channelOnly == channelNumber)
            }) {
                return match
            }
        }

        // 3. Title match fallback for series
        return rules.first(where: { rule in
            rule.isSeriesRule && rule.title.caseInsensitiveCompare(airing.title) == .orderedSame && (rule.channelOnly == nil || rule.channelOnly == channelNumber)
        })
    }
}
