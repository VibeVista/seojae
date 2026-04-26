---
title: "Intro to Large Language Models"
type: source
tags: [llm, scaling, security, AI-paradigm]
sources: ["raw/videos/intro-to-llms.md"]
aliases: []
created: 2026-04-10
updated: 2026-04-10
---

# Intro to Large Language Models

## Summary

[[Andrej Karpathy]]의 2023년 강연으로, LLM이 무엇이고 어떻게 작동하며, 어떤 능력과 한계를 가지는지, 그리고 미래 방향을 포괄적으로 소개한다. LLM의 본질을 두 개의 파일(가중치 파일 + 추론 코드)로 단순화한 설명이 특징적이다.

## Key Points

### LLM의 구조

LLM은 본질적으로 두 파일로 구성된다:
1. **가중치 파일(Weights File)**: 수십억 개 파라미터가 학습한 패턴과 지식을 인코딩
2. **추론 코드(Inference Code)**: 가중치를 사용해 토큰 단위로 텍스트를 생성하는 비교적 단순한 프로그램

### 학습 프로세스

- **Next-token prediction**: 텍스트 시퀀스에서 다음 토큰을 예측하는 단순하지만 강력한 목표
- 비지도 학습 — 수동 라벨링 없이 원시 텍스트만으로 학습
- 모델이 점진적으로 언어 구조, 사실, 추론, 패턴을 학습

### Scaling Laws

- 모델 크기, 학습 데이터, 연산 자원을 늘릴수록 성능이 계속 향상
- **알려진 상한선이 없음** — LLM이 달성할 수 있는 근본적 한계에 아직 도달하지 않았을 가능성
- 성능이 예측 가능한 멱법칙(power law)을 따름

### 보안 고려사항

- **Prompt Injection**: 조작된 프롬프트로 의도된 동작을 우회
- **Jailbreaks**: 안전 가드레일을 우회하는 적대적 기법
- **Alignment Challenges**: LLM이 인간의 가치와 의도에 따라 행동하게 하는 문제

### LLM as Operating System

Karpathy가 제시한 비전 중 하나로, LLM이 AI 시스템의 핵심 운영체제가 되는 미래:
- 다양한 도구와 기능을 조율하는 중앙 오케스트레이터
- 자연어 인터페이스를 통한 시스템 접근
- 복잡한 작업의 하위 작업 분해
- 외부 지식 베이스, 도구, API와의 통합

이 강연은 [[Software 2.0]]에서 시작된 "학습된 소프트웨어" 패러다임이 LLM 시대에 어떻게 구체화되는지를 보여주며, 나아가 [[Vibe Coding]] 같은 새로운 개발 방식의 기반을 제공한다.

## Source

- Author: [[Andrej Karpathy]]
- Date: 2023-11-22
- URL: https://www.youtube.com/watch?v=zjkBMFhNj_g
