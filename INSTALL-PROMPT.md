# Install prompt

Paste everything below the line into your coding agent, started in the project you want the runner to work on.

---

Install the runner kit for this project. Follow these steps in order.

1. Get the kit. If `~/runner-kit` exists, use it. Otherwise run `git clone REPLACE-WITH-REPOSITORY-URL ~/runner-kit`. If I named another place for the kit, use that instead.
2. Before acting, read three files in the kit in full: `manifest.yaml`, `interview.yaml` and `PROTOCOL.md`.
3. Find out what you can without asking me. Run the kit's `bin/runner-doctor` and show me its output. Then work through the `detect` steps of each question in `interview.yaml`.
4. Ask me only the questions in `interview.yaml` that you could not answer yourself. Ask one at a time, each with your recommended answer. Show me what you detected for the others in one short list and let me correct it.
5. Install by running the `install` steps of `manifest.yaml` in order, with my answers. Put each answer in the setting its question's `fills` names.
6. Run the self-test command from `manifest.yaml` and show me its output exactly as printed. It starts one small agent session, which uses a little of my plan.
7. Report success only if the last line is `SELFTEST: PASS`. If it is `SELFTEST: PARTIAL` or `SELFTEST: FAIL`, say so, show the failing line and the log path, and stop.

Rules:

- Change nothing outside the kit directory and the project I name. The one exception is question `protocol_scope` in `interview.yaml`, and only if I answer `machine`.
- Do not edit the kit's scripts. If a step cannot be followed as written, stop and tell me which step.
- Do not start the queue. Finish by telling me the next steps listed under `after_install` in `manifest.yaml`.
