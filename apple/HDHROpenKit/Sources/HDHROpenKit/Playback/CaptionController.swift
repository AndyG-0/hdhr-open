import Foundation

@MainActor
public final class CaptionController: ObservableObject {
    @Published public private(set) var activeCueText: String?
    @Published public var isEnabled: Bool = false {
        didSet {
            if !isEnabled {
                activeCueText = nil
            }
        }
    }

    private var cues: [CaptionCue] = []
    private var baseOffset: Double = 0.0

    public init() {}

    public func setCues(_ cues: [CaptionCue], baseOffset: Double = 0.0) {
        self.cues = cues
        self.baseOffset = baseOffset
    }

    public func updatePlaybackTime(_ currentTime: Double) {
        guard isEnabled, !cues.isEmpty else {
            activeCueText = nil
            return
        }

        let absoluteTime = currentTime + baseOffset
        if let matchingCue = cues.first(where: { $0.contains(time: absoluteTime) }) {
            self.activeCueText = matchingCue.text
        } else {
            self.activeCueText = nil
        }
    }
}
