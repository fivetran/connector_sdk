# Fivetran Code Review and Example Connector Guidelines


## 1. Code review principles

All guidelines in this document derive from the following simple principles:

- Code reviews should result in the best possible pull request being merged.
- Code reviews should be fast.
- Code reviews should be collaborative.
- Code reviews should result in at least two people (author + 1) fully understanding the change.

---

## 2. Pull request (PR) guidelines

### 2.1 PR sizing and testing reminders

1. Break up changes into logical pieces (e.g., using an interactive rebase).
2. Split large PRs (especially XL) into multiple smaller, logical PRs.
   - Ideally, a PR addresses one thing only.
   - For monolithic XL PRs, find a primary reviewer ahead of time who can dedicate review cycles.
   - Reject non-refactor XL PRs until they’re broken into smaller parts.
   - We currently don’t have PR sizing automation — see *Add size label* for guidance.
   - No labels are required; use sizing only to estimate and manage PR scope.
3. If functionality changes are mixed with refactoring, separate them into distinct PRs.
   - If that’s not possible, add comments directing reviewers to critical functionality changes.


### 2.2 PR authoring guidelines

1. Write a good commit message (PR title) using the following format:

    ```
    type_of_change(module/submodule): Short description
    ```

    where `type_of_change` is one of:  `feature`, `fix`, `test`, `cleanup`, `refactor`, `doc`, `flag`, `tweak`, `config`, `security`.

    Examples:
    - `feature(examples): added new example for smartsheets  ## New example`
    - `fix(examples): fixes response parsing in github example  ## Fix existing example`
    - `fix(source_examples): added comments in the examples  ## Fix multiple existing examples`

2. Write a detailed PR description, including:
- Links to relevant tickets.
- How the change was tested.
- Any additional context useful to reviewers.

3. Review your own code before submission:
- Validate naming conventions, boundary conditions, and test coverage.
- Feel free to use GitHub Copilot as a reviewer to catch basic issues early.

4. Add comments in the diff to highlight important logic or non-obvious changes.

5. Respond professionally to reviewer comments. Remember we are here to help and will strive to ask for only necessary changes to future proof your contribution and make it understandable to others.

---

## 3. Preparing code for PR submission

To adhere to Fivetran engineering standards, follow this process:

1. Write your `connector.py` solution (start from system-generated baselines if applicable).
2. Feed it to the cursor agent `connector_sdk_template` to generate `connector_test.py` following best practices.
3. Review generated revisions (e.g., ensure `fivetran debug` works).
4. Feed the project to cursor agent `connector_sdk_readme` to generate a consistent `README.md`.
5. Submit the PR.

---

## 4. Example connector guidelines

### 4.1 Template connector

A reference implementation is available here:  
[Fivetran Connector SDK Template Example](https://github.com/fivetran/connector_sdk/tree/main/template_connector)

This includes:
- A `connector.py` template.
- A `README.md` template illustrating recommended structure and conventions.

This is a great place to start to learn our coding practices through templated examples.


### 4.2 General best practices

- Import only necessary modules and libraries.
- Use clear, consistent, descriptive names for functions and variables.
- Use UPPERCASE_WITH_UNDERSCORES for constants (e.g., `CHECKPOINT_INTERVAL`).
- Keep constants private by default (e.g., `__CHECKPOINT_INTERVAL`).
- Add docstrings explaining each function’s purpose.
- Add comments for complex logic and user customization points.
- Split large functions into smaller helper functions for readability.
- Use logging judiciously — avoid excessive or redundant logs.
- Implement error handling that targets specific exceptions.
- Add retry logic (with exponential backoff) for API requests.
- Define a complete data model in the `schema()` function, with primary keys and data types.
- Avoid loading all data into memory — use pagination or streaming.
- Document pagination, upsert/update/delete, and checkpointing with clear comments.
- Checkpoint state regularly to resume from the last successful sync and cleanly send data to your warehouse.
- Refer to the [Connector SDK Best Practices](https://fivetran.com/docs/connectors/connector-sdk/best-practices).

---

## 5. Example development guidelines

### 5.1 Example principles

- Self-explanatory and well-commented code.
- Must produce working code (can require the SDK Playground).
- No identifiable customer information should be included.



### 5.2 Demonstrate one core concept

- Each example should focus on one SDK feature or pattern (e.g., incremental sync, schema discovery, error handling).
- Where possible, split complex connectors into multiple examples.



### 5.3 Avoid overloading

- Don’t demonstrate all features in one example.
- Create separate folders/examples, each with a distinct goal.
- Keep the `update()` method short — use smaller helper methods.



### 5.4 Minimal dependencies

- Include only necessary dependencies.
- Pin dependency versions in `requirements.txt`, `pyproject.toml`, or `poetry.lock`.



### 5.5 Code organization
Good code organization and clarity is a balance of this list. Do your best to adhere to each point below. 

- Keep the code easy to read and navigate.
- Use good naming instead of excessive commenting.
- Follow established commenting conventions:
  - Explain the example’s purpose.
  - Explain helper functions with inline comments.



### 5.6 Logging

- Log key steps at info level (e.g., `"Fetching page X"`).
- Avoid logs inside loops.
- Add logs for warnings and severe issues.



### 5.7 Error handling

- Catch and raise meaningful, specific exceptions.
- If demonstrating error handling, highlight it in the `README.md`.



### 5.8 Testing (optional but encouraged)

- Include a basic test file (e.g., `test_connector.py`).
- Use `pytest` or similar for validation.
- Mock external API calls so examples run without real credentials.



---

## 6. Summary

These guidelines ensure all Fivetran examples and code reviews are:
- High quality
- Easy to understand
- Consistent with best practices
- Collaborative and maintainable

Following these principles leads to faster reviews, cleaner merges, and more resilient code.

