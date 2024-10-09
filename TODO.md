# Infrastructure

- [x] bin/app.ts
  - [x] project name change
- [x] Add two source actions for code - sourceCDKCode, sourceMLCode
- [ ] lib/codePipelineConstruct.ts
  - [ ] Modify as needed
- [x] lib/dataSourceConstruct.ts
  - [x] persistent data source bucket
  - [x] cloudwatch even trigger instead of sns
- [ ] dataSourceMonitor
  - [x] Use python for lambda function
  - [ ] modify lambda function
    - [ ] belt type MAC address wise
    - [ ] manual triggering support
  - [x] dataManifest.json structure
- [ ] lib/infrastructureStack.ts
  - [ ] modify output (if needed)
  

# Model Deploy
- [ ] piplineModelFunction
  - [ ] Use python for lambda function
  - [ ] Modify lambda function


# Consumers

**Infrastructure, frontend and backend code for inference interface**

- [ ] Modify packages/data-api
- [ ] Modify packages/data-type
- [ ] Modify packages/webiste
- [ ] Modify packages/webiste-index-builder
- [ ] Modify packages/infrastructure

# README

Update documentation