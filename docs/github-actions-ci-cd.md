# GitHub Actions CI/CD

The project uses GitHub Actions to validate the repository and create a delivery artifact whenever code is pushed to `main`. The same validation also runs for pull requests targeting `main` and can be started manually from the Actions tab.

## Continuous integration

The validation job uses Python 3.9 to match the temporary EC2 dashboard environment. It installs the Streamlit dependencies, compiles the Python files under `analysis`, `glue/jobs`, and `streamlit`, and checks the syntax of the infrastructure shell scripts.

This provides an automated check that the main project code can be parsed and that the deployment scripts do not contain shell syntax errors.

## Continuous delivery

After validation succeeds on the `main` branch, the delivery job packages the tracked repository files into a ZIP. The package includes a `BUILD_INFO.txt` file with the source commit and branch. GitHub stores the ZIP with the completed workflow run for 14 days.

The delivery stage produces a traceable, deployment-ready copy of the validated repository without automatically creating AWS resources. This keeps the project cost-controlled and avoids storing long-lived AWS credentials in GitHub.

## Why GitHub Actions

GitHub Actions keeps source control and automated validation in the same platform. It provides a visible history of workflow runs, connects every delivery artifact to a Git commit, and prevents packaging from continuing when validation fails.

## Workflow file

The workflow is defined in:

```text
.github/workflows/ci-cd.yml
```

The `validate` job must pass before the `deliver` job can run.
