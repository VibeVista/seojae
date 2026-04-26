---
title: "Software 2.0"
type: concept
tags: [programming-paradigm, neural-networks, machine-learning, deep-learning]
sources: ["raw/articles/software-2.0.md"]
aliases: ["소프트웨어 2.0"]
created: 2026-04-10
updated: 2026-04-10
---

# Software 2.0

## Definition

Software 2.0는 뉴럴 네트워크가 새로운 프로그래밍 패러다임을 구성한다는 개념이다. 전통적 소프트웨어(Software 1.0)에서 인간이 명시적 코드를 작성하는 것과 달리, Software 2.0에서는 "소스 코드"가 네트워크의 가중치(weights)이며, 이 가중치는 최적화 과정(학습)을 통해 데이터로부터 학습된다.

## Origin

[[Andrej Karpathy]]가 2017년 블로그 포스트에서 처음 제안한 개념이다. 당시 Tesla AI Director로 재직하던 Karpathy는 소프트웨어 개발의 상당 부분이 이미 뉴럴 네트워크 기반으로 전환되고 있으며, 이 전환이 가속화될 것이라고 주장했다.

> *"Software 2.0 is written in neural network weights. No human is involved in writing this code because there are a lot of weights (typical networks might have millions), and coding directly in weights is kind of hard."*

## Paradigm Comparison

| 측면 | Software 1.0 | Software 2.0 |
|------|-------------|--------------|
| **소스 코드** | 인간이 작성한 명시적 명령어 (Python, C++ 등) | 뉴럴 네트워크 가중치 (최적화로 학습) |
| **프로그래머 역할** | 알고리즘 설계, 코드 작성, 디버깅 | 데이터셋 큐레이션, 아키텍처 설계, 학습 관리 |
| **도구** | IDE, 컴파일러, 디버거 | GPU 클러스터, 데이터 파이프라인, 학습 프레임워크 |
| **강점** | 논리적 규칙, 정확한 제어, 투명한 동작 | 패턴 인식, 비정형 데이터 처리, 인간 수준 인식 |

## [[Vibe Coding]]과의 관계

Software 2.0는 [[Vibe Coding]]의 개념적 전구체(conceptual precursor)이다:

- **Software 2.0** (2017): 인간이 데이터를 통해 의도를 명시하면 뉴럴 네트워크가 동작을 학습
- **[[Vibe Coding]]** (2025): 인간이 자연어로 의도를 명시하면 LLM이 코드를 생성

두 개념 모두 [[Andrej Karpathy]]가 제시했으며, **"인간은 무엇을(what) 정의하고, 기계가 어떻게(how)를 해결한다"**는 공통 원칙을 공유한다. Software 2.0가 뉴럴 네트워크를 통한 암묵적 프로그래밍의 길을 열었다면, Vibe Coding은 자연어라는 인터페이스를 통해 그 접근을 더 대중화한 것이다.

## Implications

Software 2.0가 시사하는 변화:
- **프로그래머 역할의 변화**: 코드 작성에서 데이터 큐레이션과 학습 파이프라인 관리로 이동
- **코드 검색의 변화**: GitHub 검색 대신 데이터셋과 모델 아키텍처 탐색
- **디버깅의 변화**: 라인별 코드 추적 대신 데이터셋 정제와 학습 하이퍼파라미터 조정
- **소프트웨어 스택의 재구성**: 전통적 코드베이스의 상당 부분이 뉴럴 네트워크로 대체
- **범용성**: 시각 인식, 음성 인식, 번역, 게임 등 다양한 도메인에서 Software 1.0을 압도

## Sources

- [[Software 2.0 — Karpathy]] — Karpathy의 원본 에세이 요약
- [[Vibe Coding]] — Software 2.0의 자연어 기반 진화 (관련 개념)
