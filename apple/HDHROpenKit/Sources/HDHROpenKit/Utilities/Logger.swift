import Foundation
import os

public enum Log {
    private static let subsystem = "org.hdhropen.client"

    public static let general = os.Logger(subsystem: subsystem, category: "general")
    public static let network = os.Logger(subsystem: subsystem, category: "network")
    public static let auth = os.Logger(subsystem: subsystem, category: "auth")
    public static let player = os.Logger(subsystem: subsystem, category: "player")
    public static let dvr = os.Logger(subsystem: subsystem, category: "dvr")
}
