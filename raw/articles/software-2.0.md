---
title: "Software 2.0"
author: "Andrej Karpathy"
source: "https://karpathy.medium.com/software-2-0-a64152b37c35"
date: 2017-11-11
---

# Software 2.0

## Overview

Andrej Karpathy introduces the concept of "Software 2.0" as a paradigm shift in how we write software using neural networks and machine learning.

## Key Ideas

### Software 1.0 vs Software 2.0

**Software 1.0** is the traditional programming paradigm where programmers explicitly write instructions in code. The process is: write code → compile → run → observe behavior.

**Software 2.0** is an emerging paradigm where instead of manually writing code, we specify the desired behavior implicitly through datasets. The process becomes: collect data → define architecture → train → observe predictions.

### The New Programming Paradigm

In Software 2.0, the "code" is the weights of a neural network, trained on data rather than written by hand. The programmer's role shifts from:
- Writing explicit algorithms
- Debugging line-by-line
- Manually handling edge cases

To:
- Designing network architectures
- Curating and labeling datasets
- Iterating on training procedures

### Dataset Curation as Central Task

The critical skill in Software 2.0 is dataset quality and curation. Just as Software 1.0 prioritized code quality, Software 2.0 prioritizes data quality. Poor data leads to poor models, regardless of architecture sophistication.

### Implications for Programming

This shift suggests:
- Programmers will spend more time on data engineering and labeling
- Software will become increasingly probabilistic (outputs probabilities rather than deterministic results)
- Debugging and testing methodologies must adapt to handle learned behaviors
- Traditional code review processes may become less relevant

## Broader Impact

The rise of Software 2.0 represents a fundamental change in how we solve problems, with deep implications for software engineering culture, tools, and education.
