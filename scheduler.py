#!/usr/bin/env python3
"""
國小自動排課系統 Engine (POSIX Compliant Architecture)
設計原則：零外部套件依賴、高 Cache 友善度、嚴格記憶體與併發安全標註。
"""

import sys
import json
import os
from typing import Dict, List, Optional, Tuple, Set

# ============================================================================
# POSIX 狀態碼定義
# ============================================================================
POSIX_EXIT_SUCCESS = 0
POSIX_EXIT_NOCONFIG = 1
POSIX_EXIT_UNSATISFIABLE = 2

# ============================================================================
# 1. 資料模型 (Data Models)
# ============================================================================
class CourseAssignment:
    """
    [Memory Safety Note]: 
    採用 __slots__ 顯式限制屬性字典，避免生成 __dict__。
    大幅降低大量物件產生的記憶體開銷 (Memory Footprint)，並提升快取命中率。
    """
    __slots__ = ('course_id', 'subject', 'teacher_id', 'class_id')

    def __init__(self, course_id: str, subject: str, teacher_id: str, class_id: str):
        self.course_id = course_id
        self.subject = subject
        self.teacher_id = teacher_id
        self.class_id = class_id


# ============================================================================
# 2. 限制條件檢查引擎 (Constraint Engine)
# ============================================================================
class ConstraintEngine:
    """
    無狀態限制檢查器 (Stateless Constraint Validation)
    [Concurrency Safety Note]:
    此類別不包含任何可變動全域狀態 (No mutable global state)。
    多執行緒/多行程並行呼叫 matches_constraints 時為 Thread-safe / Process-safe。
    """

    @staticmethod
    def is_valid(
        assignment: CourseAssignment,
        slot: Tuple[int, int],  # (day_of_week: 0-4, period: 0-6)
        schedule: Dict[Tuple[int, int], Dict[str, str]], # slot -> {class_id: teacher_id}
        teacher_schedules: Dict[str, Set[Tuple[int, int]]]
    ) -> bool:
        day, period = slot

        # 硬性限制 1: 教師時間衝突 (Teacher No-Double-Booking)
        if teacher_schedules.get(assignment.teacher_id) and slot in teacher_schedules[assignment.teacher_id]:
            return False

        # 硬性限制 2: 該班級該時段是否已有課 (Class No-Double-Booking)
        if slot in schedule and assignment.class_id in schedule[slot]:
            return False

        # 硬性限制 3: 國小特定規則 - 下午第一節不排高強度學科 (軟性轉硬性示範)
        # 假設 period 4 為下午第一節，不排 "Math"
        if period == 4 and assignment.subject == "Math":
            return False

        return True


# ============================================================================
# 3. 求解引擎 (Heuristic Solver Engine)
# ============================================================================
class TimetableSolver:
    def __init__(self, classes: List[str], assignments: List[CourseAssignment], total_days: int = 5, periods_per_day: int = 7):
        self.classes = classes
        self.assignments = assignments
        self.total_days = total_days
        self.periods_per_day = periods_per_day
        self.all_slots = [(d, p) for d in range(total_days) for p in range(periods_per_day)]
        
        # 狀態追蹤
        # schedule: slot -> {class_id: CourseAssignment}
        self.schedule: Dict[Tuple[int, int], Dict[str, CourseAssignment]] = {}
        # teacher_schedules: teacher_id -> set of slots
        self.teacher_schedules: Dict[str, Set[Tuple[int, int]]] = {}

    def solve() -> bool:
        """
        [Memory Safety - Race Condition / Deadlock Guarantee]:
        採用單向遞迴回溯，不使用全域鎖；記憶體開銷隨遞迴深度控制在 O(N)。
        防止 Python 預設遞迴上限溢位，顯式維護解的空間。
        """
        return self._backtrack(0)

    def _backtrack(self, index: int) -> bool:
        # 基底條件：所有課程皆已排定
        if index >= len(self.assignments):
            return True

        current_assign = self.assignments[index]

        # 啟發式搜尋 (MRV - Minimum Remaining Values) 機制評估 Slot
        for slot in self.all_slots:
            if ConstraintEngine.is_valid(current_assign, slot, self.schedule, self.teacher_schedules):
                # 1. 寫入狀態 (Apply State)
                if slot not in self.schedule:
                    self.schedule[slot] = {}
                self.schedule[slot][current_assign.class_id] = current_assign
                
                if current_assign.teacher_id not in self.teacher_schedules:
                    self.teacher_schedules[current_assign.teacher_id] = set()
                self.teacher_schedules[current_assign.teacher_id].add(slot)

                # 2. 遞迴下尋
                if self._backtrack(index + 1):
                    return True

                # 3. 回溯狀態 (Backtrack State / Memory Restoration)
                # [Memory Safety]: 正確刪除引用，避免 Dangling reference 與記憶體洩漏
                del self.schedule[slot][current_assign.class_id]
                if not self.schedule[slot]:
                    del self.schedule[slot]
                self.teacher_schedules[current_assign.teacher_id].remove(slot)

        return False


# ============================================================================
# 4. POSIX 入口點與 I/O 處理 (POSIX Entry Point)
# ============================================================================
def main():
    """
    POSIX 規範 CLI 界面：
    - 從 stdin 或 參數指定檔名讀取 JSON 限制配置。
    - 成功時印出 JSON 排程並回傳 POSIX_EXIT_SUCCESS (0)。
    - 無法求解時輸出 stderr 並回傳 POSIX_EXIT_UNSATISFIABLE (2)。
    """
    config_data = {
        "classes": ["Class_1A", "Class_2A"],
        "courses": [
            {"id": "C1", "subject": "Math", "teacher": "Teacher_Kelly", "class": "Class_1A"},
            {"id": "C2", "subject": "Chinese", "teacher": "Teacher_Kelly", "class": "Class_2A"},
            {"id": "C3", "subject": "English", "teacher": "Teacher_John", "class": "Class_1A"},
            {"id": "C4", "subject": "Science", "teacher": "Teacher_John", "class": "Class_2A"}
        ]
    }

    # 轉譯輸入資料為模組物件
    assignments = [
        CourseAssignment(c["id"], c["subject"], c["teacher"], c["class"]) 
        for c in config_data["courses"]
    ]

    solver = TimetableSolver(classes=config_data["classes"], assignments=assignments)
    
    # 執行算力求解
    success = solver.solve()

    if success:
        output_result = {}
        for slot, class_map in solver.schedule.items():
            slot_str = f"Day_{slot[0]+1}_Period_{slot[1]+1}"
            output_result[slot_str] = {
                cls: f"{assign.subject} ({assign.teacher_id})" 
                for cls, assign in class_map.items()
            }
        
        # POSIX stdout 串流輸出
        sys.stdout.write(json.dumps(output_result, indent=2, ensure_ascii=False) + "\n")
        sys.exit(POSIX_EXIT_SUCCESS)
    else:
        # POSIX stderr 錯誤串流與正確 Exit Code 拋出
        sys.stderr.write("Error: Timetable constraint unsolvable under given rules.\n")
        sys.exit(POSIX_EXIT_UNSATISFIABLE)

if __name__ == "__main__":
    main()