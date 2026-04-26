---
title: "Karpathy's Software Evolution: 1.0 → 2.0 → Vibe Coding"
type: synthesis
tags: [software-evolution, programming-paradigm, AI, neural-networks, llm]
sources: ["raw/articles/software-2.0.md", "raw/videos/intro-to-llms.md", "raw/articles/vibe-coding.md"]
aliases: []
created: 2026-04-10
updated: 2026-04-10
---

# Karpathy's Software Evolution: 1.0 → 2.0 → Vibe Coding

## Overview

[[Andrej Karpathy]]의 저술과 강연을 관통하는 핵심 서사는 소프트웨어 개발 패러다임의 진화이다. 2017년 [[Software 2.0]] 에세이에서 시작해, 2023년 LLM 강연을 거쳐, 2025년 [[Vibe Coding]]에 이르기까지, 그는 인간이 코드를 작성하는 방식이 근본적으로 변화하고 있다는 일관된 주장을 펼쳐왔다.

## The Arc: 명시적 코드에서 의도 전달로

### Phase 1: Software 1.0 — 인간이 코드를 작성한다

전통적 프로그래밍에서 인간은 알고리즘을 설계하고, 코드를 한 줄씩 작성하며, 모든 엣지 케이스를 수동으로 처리한다. 이 패러다임에서 **코드가 곧 제품**이다.

### Phase 2: [[Software 2.0]] — 데이터가 코드를 만든다 (2017)

Karpathy는 뉴럴 네트워크의 가중치가 새로운 형태의 "코드"라고 주장했다. 프로그래머의 역할이 코드 작성에서 **데이터 큐레이션과 아키텍처 설계**로 이동한다. 핵심 전환은 이렇다:

- **입력**: 명시적 명령 → 데이터셋
- **출력**: 결정론적 → 확률적
- **핵심 역량**: 코딩 스킬 → 데이터 품질 관리

### Phase 2.5: LLM 시대 — 학습이 범용화된다 (2023)

"Intro to Large Language Models" 강연은 Software 2.0의 원칙이 범용 AI로 확장된 시점을 포착한다. Next-token prediction이라는 단순한 학습 목표가 언어 이해, 추론, 코드 생성 등 다양한 능력으로 이어진다. Scaling Laws는 이 방향이 아직 한계에 도달하지 않았음을 시사한다.

특히 "LLM as Operating System" 비전은 AI가 단순한 도구를 넘어 **시스템의 중심 조율자**가 되는 미래를 제시하며, Vibe Coding의 기반을 마련한다.

### Phase 3: [[Vibe Coding]] — 자연어가 코드를 만든다 (2025)

마지막 단계에서 인간은 코드를 전혀 작성하지 않는다. 자연어로 의도를 전달하면 LLM이 코드를 생성하고, 개발자는 결과를 관찰하며 수락/거부를 반복한다. Software 2.0에서 데이터가 담당하던 "의도 전달" 역할을 이제 **자연어**가 대체한다.

## Unifying Thread: 추상화 수준의 상승

세 단계를 관통하는 핵심 패턴은 **추상화 수준의 지속적 상승**이다:

```
Software 1.0:  인간 → [코드 작성] → 프로그램
Software 2.0:  인간 → [데이터 제공] → 뉴럴 네트워크 → 동작
Vibe Coding:   인간 → [자연어 설명] → LLM → 코드 → 동작
```

각 단계에서:
1. **인간이 다루는 추상화 수준이 높아진다** (코드 → 데이터 → 자연어)
2. **기계가 처리하는 범위가 넓어진다** (실행 → 학습+실행 → 코딩+실행)
3. **코드에 대한 인간의 이해도는 낮아진다** (완전한 이해 → 부분적 해석 → 동작 관찰)

## Tensions and Trade-offs

이 진화가 순전히 긍정적인 것만은 아니다:

- **제어와 편의의 트레이드오프**: 추상화가 높아질수록 세밀한 제어가 어려워진다
- **디버깅의 어려움**: Software 1.0의 스택 트레이스 → Software 2.0의 학습 곡선 분석 → Vibe Coding의 "다시 설명해보기"
- **보안 우려**: LLM 강연에서 다룬 prompt injection, jailbreak 문제가 Vibe Coding 환경에서 더 심각해질 수 있음
- **이해도 감소**: 개발자가 자신이 만든 소프트웨어를 완전히 이해하지 못하는 상황의 확대

## Conclusion

Karpathy의 시각에서 소프트웨어 개발의 미래는 명확하다: 인간은 점점 더 **"무엇을(what)"**에 집중하고, **"어떻게(how)"**는 기계에 위임한다. Software 2.0이 이 전환의 이론적 기반을 놓았다면, LLM이 기술적 가능성을 입증했고, Vibe Coding이 실천적 워크플로우를 제시했다. 이 세 단계는 별개의 아이디어가 아니라, 하나의 일관된 비전이 시간에 따라 구체화된 결과다.

## Sources

- [[Software 2.0 — Karpathy]] — Software 2.0 에세이 요약
- [[Intro to Large Language Models]] — LLM 개론 강연 요약
- [[Vibe Coding — Karpathy]] — Vibe Coding 아티클 요약
