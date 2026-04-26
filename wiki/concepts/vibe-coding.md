---
title: "Vibe Coding"
type: concept
tags: [programming-paradigm, AI-tools, natural-language, llm]
sources: ["raw/articles/vibe-coding.md", "raw/articles/software-2.0.md"]
aliases: ["바이브 코딩"]
created: 2026-04-10
updated: 2026-04-10
---

# Vibe Coding

## Definition

Vibe Coding은 자연어 우선(natural language-first) 프로그래밍 패러다임으로, 개발자가 원하는 동작을 일상 언어로 설명하고 AI가 코드를 생성하며, 생성된 코드를 세밀하게 읽지 않고 결과 기반으로 반복 개발하는 방식이다.

## Origin

[[Andrej Karpathy]]가 2025년 2월 X(트위터) 포스트에서 처음 명명한 개념이다. 그의 표현을 빌리면:

> *"I just see stuff, say stuff, run stuff, and copy paste stuff, and it mostly works."*

이 표현은 코드에 대한 깊은 이해 없이도 소프트웨어를 만들 수 있는 새로운 접근법의 본질을 포착한다.

## [[Software 2.0]]과의 관계

Vibe Coding은 [[Software 2.0]]의 자연스러운 진화 단계로 볼 수 있다:

- **Software 2.0**: 인간이 데이터를 통해 의도를 명시하면 뉴럴 네트워크가 동작을 학습
- **Vibe Coding**: 인간이 자연어로 의도를 명시하면 LLM이 코드를 생성

두 패러다임 모두 **인간은 "무엇을(what)"에 집중하고, 기계가 "어떻게(how)"를 처리**한다는 핵심 원칙을 공유한다.

## Paradigm Comparison

| 측면 | Software 1.0 | [[Software 2.0]] | Vibe Coding |
|------|-------------|------------------|-------------|
| **코드 작성자** | 인간 프로그래머 | 뉴럴 네트워크 (가중치) | LLM |
| **입력** | 명시적 코드 | 데이터셋 + 아키텍처 | 자연어 설명 |
| **디버깅** | 라인별 추적 | 데이터/학습 조정 | 수락/거부 사이클 |
| **핵심 스킬** | 알고리즘 설계, 코딩 | 데이터 큐레이션 | 의도의 명확한 전달 |
| **결과 이해** | 완전한 이해 | 부분적 해석 가능 | 동작 관찰 기반 |
| **등장 시기** | ~ 전통적 | 2017 | 2025 |

## Characteristics

- **자연어 우선**: 코드 문법보다 명확한 설명이 중요
- **수락/거부 사이클**: 상세 디버깅 대신 이진 피드백으로 반복
- **패턴 인식 위임**: AI가 패턴을 인식하고 코드를 생성
- **실용주의**: 작동하면 사용 — 모든 구현 세부사항을 이해할 필요 없음
- **빠른 반복**: 깊은 코드 이해 오버헤드 없이 빠른 피드백 루프

## Implications

Vibe Coding이 시사하는 미래:
- 프로그래밍 스킬이 문법/알고리즘에서 **명확한 커뮤니케이션** 능력으로 이동
- AI가 기술적 코드 생성 부담을 처리
- 개발 속도의 극적 증가
- 코드 읽기가 아닌 **동작 관찰**을 통한 이해
- 프로그래밍 진입 장벽의 대폭 하락

## Sources

- [[Vibe Coding — Karpathy]] — Karpathy의 원본 아티클 요약
- [[Software 2.0 — Karpathy]] — Software 2.0 에세이 요약
