import Foundation
import CoreGraphics

public struct CaptionCue: Identifiable, Sendable, Hashable {
    public var id: String { "\(start)_\(end)_\(text)" }
    public let start: Double
    public let end: Double
    public let text: String

    public init(start: Double, end: Double, text: String) {
        self.start = start
        self.end = end
        self.text = text
    }

    public func contains(time: Double) -> Bool {
        time >= start && time <= end
    }
}

public struct ThumbnailCue: Identifiable, Sendable, Hashable {
    public var id: String { "\(start)_\(end)_\(x)_\(y)" }
    public let start: Double
    public let end: Double
    public let x: Int
    public let y: Int
    public let width: Int
    public let height: Int
    public let imageURL: String?

    public init(start: Double, end: Double, x: Int, y: Int, width: Int, height: Int, imageURL: String? = nil) {
        self.start = start
        self.end = end
        self.x = x
        self.y = y
        self.width = width
        self.height = height
        self.imageURL = imageURL
    }

    public var cropRect: CGRect {
        CGRect(x: x, y: y, width: width, height: height)
    }

    public func contains(time: Double) -> Bool {
        time >= start && time <= end
    }
}

public enum VTTParser {
    public static func parseTime(_ timeString: String) -> Double? {
        let parts = timeString.trimmingCharacters(in: .whitespaces).components(separatedBy: ":")
        guard parts.count == 2 || parts.count == 3 else { return nil }

        if parts.count == 2 {
            guard let minutes = Double(parts[0]),
                  let seconds = Double(parts[1].replacingOccurrences(of: ",", with: ".")) else {
                return nil
            }
            return minutes * 60.0 + seconds
        } else {
            guard let hours = Double(parts[0]),
                  let minutes = Double(parts[1]),
                  let seconds = Double(parts[2].replacingOccurrences(of: ",", with: ".")) else {
                return nil
            }
            return hours * 3600.0 + minutes * 60.0 + seconds
        }
    }

    public static func parseCaptions(from vttString: String) -> [CaptionCue] {
        var cues: [CaptionCue] = []
        let lines = vttString.components(separatedBy: .newlines)
        var i = 0

        while i < lines.count {
            let line = lines[i].trimmingCharacters(in: .whitespaces)
            if line.contains("-->") {
                let timeParts = line.components(separatedBy: "-->")
                if timeParts.count == 2 {
                    let startStr = timeParts[0].trimmingCharacters(in: .whitespaces)
                    let endStr = timeParts[1].trimmingCharacters(in: .whitespaces).components(separatedBy: " ")[0]
                    if let start = parseTime(startStr), let end = parseTime(endStr) {
                        var textLines: [String] = []
                        i += 1
                        while i < lines.count && !lines[i].trimmingCharacters(in: .whitespaces).isEmpty {
                            textLines.append(lines[i].trimmingCharacters(in: .whitespaces))
                            i += 1
                        }
                        let text = textLines.joined(separator: "\n")
                        if !text.isEmpty {
                            cues.append(CaptionCue(start: start, end: end, text: text))
                        }
                    }
                }
            }
            i += 1
        }
        return cues
    }

    public static func parseThumbnailVtt(from vttString: String) -> [ThumbnailCue] {
        var cues: [ThumbnailCue] = []
        let lines = vttString.components(separatedBy: .newlines)
        var i = 0

        while i < lines.count {
            let line = lines[i].trimmingCharacters(in: .whitespaces)
            if line.contains("-->") {
                let timeParts = line.components(separatedBy: "-->")
                if timeParts.count == 2 {
                    let startStr = timeParts[0].trimmingCharacters(in: .whitespaces)
                    let endStr = timeParts[1].trimmingCharacters(in: .whitespaces).components(separatedBy: " ")[0]
                    if let start = parseTime(startStr), let end = parseTime(endStr) {
                        i += 1
                        if i < lines.count {
                            let mediaLine = lines[i].trimmingCharacters(in: .whitespaces)
                            if let xywhRange = mediaLine.range(of: "#xywh=") {
                                let imagePart = String(mediaLine[..<xywhRange.lowerBound])
                                let coordsPart = String(mediaLine[xywhRange.upperBound...])
                                let coords = coordsPart.components(separatedBy: ",").compactMap { Int($0) }
                                if coords.count == 4 {
                                    cues.append(ThumbnailCue(
                                        start: start,
                                        end: end,
                                        x: coords[0],
                                        y: coords[1],
                                        width: coords[2],
                                        height: coords[3],
                                        imageURL: imagePart
                                    ))
                                }
                            }
                        }
                    }
                }
            }
            i += 1
        }
        return cues
    }
}
