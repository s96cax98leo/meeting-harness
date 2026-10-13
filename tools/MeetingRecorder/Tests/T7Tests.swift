// Tests/T7Tests.swift —— t7 實機驗收發現的修正（spec §6 第 102–106 條）
import Foundation
import CoreGraphics

let mrtT7Tests: [MRTCase] = [
    ("testControlFeedback", testControlFeedback),
    ("testStatusItemObscured", testStatusItemObscured),
]

// §6 第 105 條：快捷鍵切換靜音、暫停、標記後要有通知回饋（圖示被瀏海擋住時也知道按到了）
func testControlFeedback() throws {
    mrtEqual(controlFeedback(.mute, markerSeq: 0), "麥克風已靜音")
    mrtEqual(controlFeedback(.unmute, markerSeq: 0), "麥克風已取消靜音")
    mrtEqual(controlFeedback(.pause, markerSeq: 0), "已暫停錄製")
    mrtEqual(controlFeedback(.resume, markerSeq: 0), "已繼續錄製")
    mrtEqual(controlFeedback(.mark, markerSeq: 3), "已加標記 3")
}

// §6 第 106 條：圖示的 x 範圍落在瀏海（auxiliaryTopLeftArea 右緣到 auxiliaryTopRightArea 左緣）內、
// 或視窗不可見時，判定被擋住；沒有瀏海的螢幕只看可見與否
func testStatusItemObscured() throws {
    let left: CGFloat = 660, right: CGFloat = 850
    mrtEqual(statusItemObscured(itemMinX: 700, itemMaxX: 760, visible: true, notchMinX: left, notchMaxX: right), true, "整個在瀏海內")
    mrtEqual(statusItemObscured(itemMinX: 640, itemMaxX: 700, visible: true, notchMinX: left, notchMaxX: right), true, "部分壓到瀏海")
    mrtEqual(statusItemObscured(itemMinX: 900, itemMaxX: 960, visible: true, notchMinX: left, notchMaxX: right), false, "瀏海右邊")
    mrtEqual(statusItemObscured(itemMinX: 600, itemMaxX: 650, visible: true, notchMinX: left, notchMaxX: right), false, "瀏海左邊（選單列左半，仍看得到）")
    mrtEqual(statusItemObscured(itemMinX: 900, itemMaxX: 960, visible: false, notchMinX: left, notchMaxX: right), true, "不可見")
    mrtEqual(statusItemObscured(itemMinX: 700, itemMaxX: 760, visible: true, notchMinX: nil, notchMaxX: nil), false, "沒有瀏海")
    mrtEqual(statusItemObscured(itemMinX: 700, itemMaxX: 760, visible: false, notchMinX: nil, notchMaxX: nil), true, "沒有瀏海但不可見")
    mrtEqual(statusItemObscured(itemMinX: 0, itemMaxX: 0, visible: true, notchMinX: left, notchMaxX: right), true, "寬度 0（還沒放上選單列）")
}
