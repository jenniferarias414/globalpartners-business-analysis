# Streamlit EC2 Deployment

The Streamlit dashboard was deployed temporarily to Amazon EC2 so the Athena-backed application could be validated in AWS without depending on local credentials or a local process.

## Deployment design

- Amazon Linux 2023 `t3.micro` instance with encrypted EBS storage.
- IMDSv2 required for instance metadata access.
- IAM instance role granting only the Athena, Glue Catalog, and S3 access needed by the dashboard.
- No static AWS access keys stored on the instance.
- No SSH ingress rule. Systems Manager was used for remote updates.
- Streamlit port 8501 restricted to one public `/32` IP address.
- A `systemd` service kept the dashboard running and restarted it after failures.

## Validation

The deployment validator confirmed the instance state, instance type, subnet, IAM profile, security group, EC2 status checks, and Streamlit health endpoint. The four dashboard views loaded successfully against the Athena Gold tables.

A compatibility issue appeared because Python 3.9 installed Streamlit 1.50.0, which did not support the newer `width="stretch"` argument used locally. Replacing it with `use_container_width=True` allowed the same dashboard code to work in both environments.

## Cost control

The EC2 instance was used only for final validation, screenshots, and the walkthrough. After evidence was captured, the instance, security group, instance profile, and IAM role were removed with the project teardown script.

## Main lesson

Application validation needs to include the actual deployment runtime. A locally successful dashboard can still expose Python or library-version differences in EC2. Matching runtime versions and keeping a repeatable update and teardown process reduces that risk.
