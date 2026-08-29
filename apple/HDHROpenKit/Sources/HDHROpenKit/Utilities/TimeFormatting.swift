import Foundation

public enum TimeFormatting {
    private static let timeFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.timeStyle = .short
        return formatter
    }()

    private static let shortTimeFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "h:mm a"
        return formatter
    }()

    private static let dayDateFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.dateFormat = "EEE, MMM d"
        return formatter
    }()

    public static func formatTime(_ timestamp: TimeInterval?) -> String {
        guard let ts = timestamp, ts > 0 else { return "" }
        let date = Date(timeIntervalSince1970: ts)
        return timeFormatter.string(from: date)
    }

    public static func formatTimeRange(start: TimeInterval?, end: TimeInterval?) -> String {
        guard let start = start else { return "" }
        let startStr = formatTime(start)
        guard let end = end else { return startStr }
        let endStr = formatTime(end)
        return "\(startStr) – \(endStr)"
    }

    public static func formatDayDate(_ timestamp: TimeInterval?) -> String {
        guard let ts = timestamp, ts > 0 else { return "" }
        let date = Date(timeIntervalSince1970: ts)
        return dayDateFormatter.string(from: date)
    }

    public static func formatDuration(seconds: Double) -> String {
        let totalSeconds = Int(seconds)
        let hours = totalSeconds / 3600
        let minutes = (totalSeconds % 3600) / 60
        let secs = totalSeconds % 60

        if hours > 0 {
            return String(format: "%d:%02d:%02d", hours, minutes, secs)
        } else {
            return String(format: "%d:%02d", minutes, secs)
        }
    }
}
