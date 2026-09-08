import HDHROpenKit
import SwiftUI
import ViewInspector
import XCTest
@testable import HDHROpenTV

@MainActor
final class TVRecordingRulesViewTests: XCTestCase {
    private func makeRule(
        id: String = "r1",
        title: String = "Morning Show",
        channelOnly: String? = nil,
        dateTimeOnly: TimeInterval? = nil,
        keywordQuery: String? = nil,
        titleMatchMode: String? = nil,
        recentOnly: Int? = nil,
        maxEpisodesToKeep: Int? = nil,
        startPadding: Int? = nil,
        endPadding: Int? = nil,
        provider: String? = nil
    ) -> HDHomeRunRecordingRule {
        HDHomeRunRecordingRule(
            recordingRuleId: id,
            seriesId: "SH123",
            title: title,
            channelOnly: channelOnly,
            dateTimeOnly: dateTimeOnly,
            startPadding: startPadding,
            endPadding: endPadding,
            recentOnly: recentOnly,
            maxEpisodesToKeep: maxEpisodesToKeep,
            titleMatchMode: titleMatchMode,
            keywordQuery: keywordQuery,
            provider: provider
        )
    }

    func testShowsEmptyStateWhenNoRules() throws {
        let view = TVRecordingRulesView(rules: [], onDeleteRule: { _ in }, onDismiss: {})

        XCTAssertNoThrow(try view.inspect().find(text: "No active recording rules scheduled"))
    }

    func testShowsRuleListWhenRulesExist() throws {
        let view = TVRecordingRulesView(rules: [makeRule()], onDeleteRule: { _ in }, onDismiss: {})

        XCTAssertNoThrow(try view.inspect().find(text: "Morning Show"))
        XCTAssertThrowsError(try view.inspect().find(text: "No active recording rules scheduled"))
    }

    func testShowsSeriesRuleBadgeWhenNoDateTime() throws {
        let view = TVRecordingRulesView(rules: [makeRule(dateTimeOnly: nil)], onDeleteRule: { _ in }, onDismiss: {})

        XCTAssertNoThrow(try view.inspect().find(text: "Series Rule"))
    }

    func testShowsSingleEpisodeBadgeWhenDateTimeSet() throws {
        let view = TVRecordingRulesView(rules: [makeRule(dateTimeOnly: Date().timeIntervalSince1970)], onDeleteRule: { _ in }, onDismiss: {})

        XCTAssertNoThrow(try view.inspect().find(text: "Single Episode"))
    }

    func testShowsKeywordAndContainsBadges() throws {
        let rule = makeRule(keywordQuery: "playoffs", titleMatchMode: "contains")
        let view = TVRecordingRulesView(rules: [rule], onDeleteRule: { _ in }, onDismiss: {})

        XCTAssertNoThrow(try view.inspect().find(text: "Keyword: playoffs"))
        XCTAssertNoThrow(try view.inspect().find(text: "Contains match"))
    }

    func testShowsChannelWhenChannelOnlySet() throws {
        let view = TVRecordingRulesView(rules: [makeRule(channelOnly: "5.1")], onDeleteRule: { _ in }, onDismiss: {})

        XCTAssertNoThrow(try view.inspect().find(text: "Channel 5.1"))
    }

    func testShowsRetentionBadge() throws {
        let view = TVRecordingRulesView(rules: [makeRule(maxEpisodesToKeep: 5)], onDeleteRule: { _ in }, onDismiss: {})

        XCTAssertNoThrow(try view.inspect().find(text: "Keep last 5"))
    }

    func testTappingDeleteInvokesOnDeleteRuleWithId() throws {
        var deletedId: String?
        let view = TVRecordingRulesView(rules: [makeRule(id: "r42")], onDeleteRule: { id in deletedId = id }, onDismiss: {})

        try view.inspect().find(button: "Delete").tap()

        XCTAssertEqual(deletedId, "r42")
    }

    func testTappingCloseInvokesOnDismiss() throws {
        var dismissed = false
        let view = TVRecordingRulesView(rules: [], onDeleteRule: { _ in }, onDismiss: { dismissed = true })

        try view.inspect().find(button: "Close").tap()

        XCTAssertTrue(dismissed)
    }

    func testShowsAddKeywordRuleButton() throws {
        let view = TVRecordingRulesView(rules: [], onDeleteRule: { _ in }, onDismiss: {})

        XCTAssertNoThrow(try view.inspect().find(button: "Add Keyword Rule"))
    }
}
