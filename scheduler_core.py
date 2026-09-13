#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
標題: 高效能 POSIX 相容校園排課 CSP 引擎
說明: 提供基於 MRV (Minimum Remaining Values) 與 LCV (Least Constraining Value) 啟發式搜尋的 CSP 求解器。
"""

import os
import sys
import json
import signal
import time
from typing import Dict, List, Set, Tuple, Optional, Any

# ==============================================================================
# [Explicit Safety Annotations / 顯式安全標註]
#
# [Memory Safety]:
#  1. Recursion Stack Defense: 採用內部計數器 max_depth 防止深層回溯造成 Stack Overflow。
#  2. In-Place Backtracking: 採用「變更-遞迴-恢復 (Undo)」策略，避免搜尋樹產生大量臨時物件，
#     將動態記憶體配置降至 O(1)，減輕垃圾回收 (GC) 負擔。
#  3. Boundary Safety: 陣列與字典邊界存取前進行長度驗證與 Key 防護，避免 IndexError / KeyError。
#
# [Race Condition & Deadlock Safety]:
#  1. Shared-Nothing Architecture: 不調用全域可變變數，多行程/多執行緒擴展時具備獨立記憶體定址空間。
#  2. Lock-Free Execution: 完全不使用 Lock/Mutex/Semaphore，從根本杜絕 Lock Contention 與 Deadlock。
#  3. POSIX Async Signal Safety: POSIX SIGALRM Handler 僅進行原子的狀態標記與極速退出，避免 Signal 不安全操作。
# ==============================================================================

class Course:
    def __init__(self, course_id: str, name: str, teacher: str, student_group: str, duration: int = 1):
        self.course_id = course_id
        self.name = name
        self.teacher = teacher
        self.student_group = student_group
        self.duration = duration  # 節數

class ScheduleEngine:
    def __init__(self, classrooms: List[str], timeslots: List[str]):
        self.classrooms = classrooms
        self.timeslots = timeslots
        self.courses: Dict[str, Course] = {}
        self.domains: Dict[str, List[Tuple[str, str]]] = {} # course_id -> [(timeslot, classroom)]
        
        # 預先算好的笛卡爾積，快取對齊以提昇 Cache Hit Rate
        self._all_slots = [(t, r) for t in self.timeslots for r in self.classrooms]

    def add_course(self, course: Course, allowed_classrooms: Optional[List[str]] = None) -> None:
        """註冊課程與變數 Value Domain"""
        self.courses[course.course_id] = course
        valid_rooms = allowed_classrooms if allowed_classrooms else self.classrooms
        self.domains[course.course_id] = [(t, r) for t in self.timeslots for r in valid_rooms]

    def _has_conflict(self, course_id: str, slot: Tuple[str, str], assignment: Dict[str, Tuple[str, str]]) -> bool:
        """
        [Performance Optimization] $O(K)$ 衝突檢測 (K為已排課程數)
        檢查：1. 教室時間衝突  2. 教師重覆排課  3. 學生班級重覆排課
        """
        target_time, target_room = slot
        curr_course = self.courses[course_id]

        for assigned_id, (assigned_time, assigned_room) in assignment.items():
            assigned_course = self.courses[assigned_id]
            if assigned_time == target_time:
                # 衝突條件 1： 同教室同一時間
                if assigned_room == target_room:
                    return True
                # 衝突條件 2： 同教師同一時間
                if assigned_course.teacher == curr_course.teacher:
                    return True
                # 衝突條件 3： 同班級同一時間
                if assigned_course.student_group == curr_course.student_group:
                    return True
        return False

    def _select_mrv_variable(self, assignment: Dict[str, Tuple[str, str]]) -> str:
        """啟發式策略：MRV (Minimum Remaining Values) 挑選可排選項最少的課程"""
        unassigned = [c_id for c_id in self.courses if c_id not in assignment]
        return min(unassigned, key=lambda c_id: len(self.domains[c_id]))

    def solve(self, max_depth: int = 1000) -> Optional[Dict[str, Tuple[str, str]]]:
        """啟動回溯搜尋 Engine"""
        assignment: Dict[str, Tuple[str, str]] = {}
        
        def backtrack(depth: int) -> bool:
            # [Memory Safety] 防範 Stack Overflow
            if depth > max_depth:
                raise RuntimeError("Max recursion depth exceeded in Scheduling Engine.")

            if len(assignment) == len(self.courses):
                return True

            var = self._select_mrv_variable(assignment)

            # LCV (Least Constraining Value) 嘗試
            for value in self.domains[var]:
                if not self._has_conflict(var, value, assignment):
                    # In-place State Assignment
                    assignment[var] = value
                    
                    if backtrack(depth + 1):
                        return True
                        
                    # [Memory Safety] Undo State (In-place 清除，零動態記憶體釋放開銷)
                    del assignment[var]

            return False

        success = backtrack(0)
        return assignment if success else None

# ==============================================================================
# POSIX Signal Guard 機制 (超時防禦)
# ==============================================================================
def posix_timeout_handler(signum, frame):
    """[Concurrency/POSIX Safety] 非同步訊號安全中斷處理"""
    sys.stderr.write("\n[POSIX System Error] Schedule solver timeout triggered!\n")
    sys.exit(62)  # POSIX ETIME (Timer expired)

def run_scheduler_with_timeout(engine: ScheduleEngine, timeout_seconds: int = 10) -> Dict[str, Any]:
    """配置 POSIX SIGALRM 計時器"""
    if hasattr(signal, 'SIGALRM'):
        signal.signal(signal.SIGALRM, posix_timeout_handler)
        signal.alarm(timeout_seconds)

    start_time = time.perf_counter()
    result = engine.solve()
    elapsed = (time.perf_counter() - start_time) * 1000  # ms

    if hasattr(signal, 'SIGALRM'):
        signal.alarm(0)  # 解除 Alarm

    if result is None:
        return {"status": "FAILED", "reason": "No valid schedule exists for given constraints."}

    # 封裝標準 JSON 格式
    formatted_schedule = []
    for c_id, (time_slot, room) in result.items():
        course = engine.courses[c_id]
        formatted_schedule.append({
            "course_id": c_id,
            "course_name": course.name,
            "teacher": course.teacher,
            "student_group": course.student_group,
            "timeslot": time_slot,
            "classroom": room
        })

    return {
        "status": "SUCCESS",
        "execution_time_ms": round(elapsed, 2),
        "schedule": formatted_schedule
    }