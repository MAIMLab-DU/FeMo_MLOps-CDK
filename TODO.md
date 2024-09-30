# Infrastructure

-[ ] bin/app.ts
    -[ ] project name change
    -[ ] git only
-[ ] dataSourceMonitor
    -[ ] modify lambda function
    -[ ] dataManifest.json structure
-[ ] lib/dataSourceConstruct.ts
    -[ ] persistent data source bucket
    -[ ] sns topic modify (if needed)
-[ ] lib/codePipelineConstruct.ts
    -[ ] Approval stage before ML-Pipeline
-[ ] lib/infrastructureStack.ts
    -[ ] modify output (if needed)


# Consumers

**Infrastructure, frontend and backend code for inference interface**

-[ ] Modify packages/data-api
-[ ] Modify packages/data-type
-[ ] Modify packages/webiste
-[ ] Modify packages/webiste-index-builder
-[ ] Modify packages/infrastructure