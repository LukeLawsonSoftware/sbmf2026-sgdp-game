# SGDP Game

## Description

A repository containing the source code for a program that can convert a JSON configuration file representing an Stochastic Generalised Dining Philosophers game instance into PRISM-games source code.

## Usage

### Generating PRISM-games source code

Given a JSON configuration file representing a SGDP game instance, generate a `.prism` file with the PRISM-game modelling lamnguage source code implementing the instance. 

`python src/generate_source.py <config-file-path> <output-file-path>`

**Example:** 

`python src/generate_source.py examples/simple-config.json simple.prism`


## Configuration file structure

### Resources

Resources are provided as an array of objects under key `"resources"` and require a `"name"` (integer) and optionally a `"failure_rate"`. If the latter is not provided, it will be a required input to the `.prism` program at execution.

### Agents

Resources are provided as an array of objects under key `"agents"` and require a `"name"` (integer), a `"demand"` (integer), and a list of `"accessible_resources"` (a list of integers corresponding to the resource `"name"`'s the agent has access to)