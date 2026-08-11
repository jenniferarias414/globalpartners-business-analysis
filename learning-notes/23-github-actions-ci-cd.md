# GitHub Actions CI/CD

GitHub Actions provides automated source validation and continuous delivery for the project.

## Continuous integration

The workflow runs for pushes and pull requests targeting `main` and can also be started manually. It checks out the repository, configures Python 3.9, installs the Streamlit dependencies, compiles the Python code, and validates the infrastructure shell scripts with `bash -n`.

These checks do not create AWS resources or run cloud jobs. They verify that the tracked code can be parsed in a clean environment and that the documented dependencies can be installed.

## Continuous delivery

After validation succeeds on `main`, a dependent delivery job packages the tracked repository files into a ZIP. The package includes build metadata with the source commit and branch, and GitHub attaches it to the completed workflow run for 14 days.

This project uses continuous delivery rather than automatic AWS deployment. The EC2 environment was temporary, so automatically creating or updating AWS resources after every push would add cost and require broader GitHub-to-AWS permissions.

## Why it matters

The workflow provides a visible validation history, stops delivery when validation fails, and connects every generated package to a specific Git commit. It also completes the project without storing long-lived AWS credentials in GitHub.
