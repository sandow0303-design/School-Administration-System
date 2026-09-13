#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import sys
from scheduler_core import ScheduleEngine, Course, run_scheduler_with_timeout

def main():
    # 預設基礎場景配置
    classrooms = ["301多媒體教室", "302一般教室", "401實驗室"]
    timeslots = [
        "週一 09:00-10:00", "週一 10:00-11:00", 
        "週二 09:00-10:00", "週二 10:00-11:00",
        "週三 14:00-15:00"
    ]

    engine = ScheduleEngine(classrooms, timeslots)

    # 載入課程資料
    courses = [
        Course("CS101", "高級 C 語言程式設計", "張教授", "資訊系一年級"),
        Course("CS102", "POSIX 作業系統實務", "李教授", "資訊系二年級"),
        Course("CS103", "電腦網路與 Socket", "張教授", "資訊系二年級"),
        Course("EE201", "數位電路實驗", "王教授", "電機系一年級"),
        Course("CS104", "資料結構與演算法", "陳教授", "資訊系一年級"),
    ]

    for c in courses:
        engine.add_course(c)

    # 執行運算（設 5 秒硬性超時）
    output = run_scheduler_with_timeout(engine, timeout_seconds=5)

    # 輸出至 stdout 供 CI 流水線補捉
    print(json.dumps(output, ensure_ascii=False, indent=2))

    if output["status"] != "SUCCESS":
        sys.exit(1)

if __name__ == "__main__":
    main()