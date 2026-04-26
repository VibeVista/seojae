---
title: "Software 2.0 — Karpathy"
type: source
tags: [neural-networks, programming-paradigm, machine-learning]
sources: ["raw/articles/software-2.0.md"]
aliases: []
created: 2026-04-10
updated: 2026-04-10
---

# Software 2.0

## Summary

[[Andrej Karpathy]]가 2017년 Medium 글에서 제시한 "Software 2.0" 개념은 소프트웨어 개발 패러다임의 근본적인 전환을 설명한다. 전통적인 **Software 1.0**에서 프로그래머가 명시적으로 코드를 작성하는 반면, **Software 2.0**에서는 데이터셋을 통해 원하는 동작을 암묵적으로 정의하고, 뉴럴 네트워크의 가중치가 "코드" 역할을 한다.

## Key Points

### 패러다임 전환

- **Software 1.0**: 코드 작성 → 컴파일 → 실행 → 동작 관찰
- **Software 2.0**: 데이터 수집 → 아키텍처 설계 → 학습 → 예측 관찰

### 프로그래머 역할의 변화

Software 2.0에서 프로그래머의 핵심 역할이 바뀐다:
- 명시적 알고리즘 작성 → 네트워크 아키텍처 설계
- 라인별 디버깅 → 데이터셋 큐레이션 및 라벨링
- 수동 엣지 케이스 처리 → 학습 절차 반복

### 데이터 큐레이션의 중요성

Software 1.0이 코드 품질을 우선시하듯, Software 2.0은 **데이터 품질**을 우선시한다. 아키텍처가 아무리 정교해도 데이터가 부실하면 모델도 부실해진다.

### 시사점

- 프로그래머들이 데이터 엔지니어링과 라벨링에 더 많은 시간을 투입하게 됨
- 소프트웨어가 점차 확률적(probabilistic) 결과를 출력
- 디버깅과 테스트 방법론이 학습된 동작을 다루도록 적응 필요
- 전통적 코드 리뷰 프로세스의 관련성이 감소

이 개념은 이후 [[Vibe Coding]]으로 이어지는 소프트웨어 개발 패러다임 진화의 핵심 단계로 자리잡는다.

## Source

- Author: [[Andrej Karpathy]]
- Date: 2017-11-11
- URL: https://karpathy.medium.com/software-2-0-a64152b37c35
