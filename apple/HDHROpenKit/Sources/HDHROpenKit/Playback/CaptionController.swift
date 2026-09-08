import Foundation

@MainActor
public final class CaptionController: ObservableObject {
    @Published public private(set) var activeCueText: String?
    @Published public var isEnabled = false {
        didSet {
            if !isEnabled {
                activeCueText = nil
            }
        }
    }

    var cues: [CaptionCue] = []
    private var baseOffset = 0.0

    public init() {}

    public func setCues(_ cues: [CaptionCue], baseOffset: Double = 0.0) {
        self.cues = cues
        self.baseOffset = baseOffset
    }

    public func reset() {
        cues = []
        baseOffset = 0.0
        activeCueText = nil
    }

    public func updatePlaybackTime(_ currentTime: Double) {
        guard isEnabled, !cues.isEmpty else {
            activeCueText = nil
            return
        }

        let absoluteTime = currentTime + baseOffset
        if let matchingCue = cues.first(where: { $0.contains(time: absoluteTime) }) {
            activeCueText = matchingCue.text
        } else {
            activeCueText = nil
        }
    }
}
