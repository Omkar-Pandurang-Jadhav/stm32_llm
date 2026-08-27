import json
import subprocess
import tempfile
from pathlib import Path
from collections import Counter
import time


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

PREDICTIONS = (
    BASE_DIR /
    "test_results" /
    "stm32_qwen_test_predictions.jsonl"
)

RESULT_DIR = (
    BASE_DIR /
    "compile_results_qwen"
)

RESULT_DIR.mkdir(exist_ok=True)


# ============================================================
# TOOLCHAIN
# ============================================================

ARM_GCC = (
    "/Applications/"
    "ArmGNUToolchain/"
    "15.3.rel1/"
    "arm-none-eabi/"
    "bin/"
    "arm-none-eabi-gcc"
)


# ============================================================
# STM32 CMSIS
# ============================================================

CMSIS_CORE = (
    "/Users/omkar/Documents/"
    "STM32CubeF1/"
    "Drivers/CMSIS/Include"
)

CMSIS_DEVICE = (
    "/Users/omkar/Documents/"
    "STM32CubeF1/"
    "Drivers/CMSIS/Device/ST/"
    "STM32F1xx/Include"
)


# ============================================================
# COMPILER FLAGS
# EXACTLY THE SAME AS ORIGINAL EVALUATOR
# ============================================================

COMPILE_FLAGS = [
    ARM_GCC,

    "-mcpu=cortex-m3",
    "-mthumb",
    "-mfloat-abi=soft",

    "-DSTM32F103xB",

    f"-I{CMSIS_CORE}",
    f"-I{CMSIS_DEVICE}",

    "-c",
]


# ============================================================
# CHECK TOOLCHAIN
# ============================================================

def check_toolchain():

    if not Path(ARM_GCC).exists():
        raise FileNotFoundError(
            f"ARM GCC not found:\n{ARM_GCC}"
        )

    result = subprocess.run(
        [ARM_GCC, "--version"],
        capture_output=True,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Could not execute ARM GCC:\n"
            + result.stderr
        )

    print(result.stdout.splitlines()[0])


# ============================================================
# COMPILE ONE EXAMPLE
# ============================================================

def compile_code(code):

    with tempfile.TemporaryDirectory(
        prefix="stm32_qwen_compile_"
    ) as temp_dir:

        temp_dir = Path(temp_dir)

        source_file = temp_dir / "main.c"
        object_file = temp_dir / "main.o"

        source_file.write_text(
            code,
            encoding="utf-8"
        )

        command = (
            COMPILE_FLAGS
            + [
                str(source_file),
                "-o",
                str(object_file)
            ]
        )

        result = subprocess.run(
            command,
            capture_output=True,
            text=True
        )

        return (
            result.returncode == 0,
            result.stdout,
            result.stderr
        )


# ============================================================
# ERROR CLASSIFICATION
# ============================================================

def classify_error(stderr):

    text = stderr.lower()

    if "no such file or directory" in text:
        return "header_or_file"

    if "fatal error" in text:
        return "fatal_error"

    if "undeclared" in text:
        return "undeclared_identifier"

    if "not declared" in text:
        return "undeclared_identifier"

    if "no member named" in text:
        return "invalid_register"

    if "has no member" in text:
        return "invalid_register"

    if "expected" in text:
        return "syntax"

    if "invalid operands" in text:
        return "type_or_operator"

    if "incompatible" in text:
        return "type_error"

    if "implicit declaration" in text:
        return "missing_function"

    if "warning:" in text and "error:" not in text:
        return "warning_only"

    return "other"


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("STM32F103VB QWEN PREDICTION COMPILATION")
    print("=" * 70)

    if not PREDICTIONS.exists():
        raise FileNotFoundError(
            f"Predictions not found:\n{PREDICTIONS}"
        )

    check_toolchain()

    print()
    print("Predictions:", PREDICTIONS)
    print("Compiler   :", ARM_GCC)
    print()

    # --------------------------------------------------------
    # LOAD PREDICTIONS
    # --------------------------------------------------------

    with open(PREDICTIONS, encoding="utf-8") as f:

        records = [
            json.loads(line)
            for line in f
            if line.strip()
        ]

    print("Loaded predictions:", len(records))
    print()

    # --------------------------------------------------------
    # OUTPUT FILES
    # --------------------------------------------------------

    all_results_file = (
        RESULT_DIR /
        "compilation_results.jsonl"
    )

    passed_file = (
        RESULT_DIR /
        "passed.jsonl"
    )

    failed_file = (
        RESULT_DIR /
        "failed.jsonl"
    )

    summary_file = (
        RESULT_DIR /
        "summary.json"
    )

    # --------------------------------------------------------
    # CLEAN OLD RESULTS
    # --------------------------------------------------------

    for path in [
        all_results_file,
        passed_file,
        failed_file,
        summary_file
    ]:

        if path.exists():
            path.unlink()

    # --------------------------------------------------------
    # COMPILE
    # --------------------------------------------------------

    passed = 0
    failed = 0

    error_categories = Counter()

    start_time = time.time()

    with open(
        all_results_file,
        "w",
        encoding="utf-8"
    ) as all_f, open(
        passed_file,
        "w",
        encoding="utf-8"
    ) as pass_f, open(
        failed_file,
        "w",
        encoding="utf-8"
    ) as fail_f:

        for i, record in enumerate(records, 1):

            code = record.get(
                "generated_code",
                ""
            )

            success, stdout, stderr = compile_code(code)

            result = {
                "index": record.get("index", i - 1),
                "prompt": record.get("prompt", ""),
                "success": success,
                "error_category": (
                    None
                    if success
                    else classify_error(stderr)
                ),
                "stderr": stderr,
                "stdout": stdout,
                "generated_code": code
            }

            line = json.dumps(
                result,
                ensure_ascii=False
            )

            all_f.write(line + "\n")

            if success:

                passed += 1
                pass_f.write(line + "\n")

            else:

                failed += 1
                fail_f.write(line + "\n")

                error_categories[
                    result["error_category"]
                ] += 1

            if i % 25 == 0 or i == len(records):

                print(
                    f"[{i}/{len(records)}] "
                    f"Passed={passed} "
                    f"Failed={failed}"
                )

    # --------------------------------------------------------
    # SUMMARY
    # --------------------------------------------------------

    elapsed = time.time() - start_time

    total = len(records)

    success_rate = (
        passed / total * 100
        if total
        else 0
    )

    failure_rate = (
        failed / total * 100
        if total
        else 0
    )

    summary = {
        "dataset": str(PREDICTIONS),
        "compiler": ARM_GCC,
        "total": total,
        "passed": passed,
        "failed": failed,
        "success_rate_percent": round(
            success_rate,
            2
        ),
        "failure_rate_percent": round(
            failure_rate,
            2
        ),
        "elapsed_seconds": round(
            elapsed,
            2
        ),
        "error_categories": dict(
            error_categories
        )
    }

    with open(
        summary_file,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            summary,
            f,
            indent=2
        )

    print()
    print("=" * 70)
    print("COMPILATION COMPLETE")
    print("=" * 70)

    print(
        f"Total             : {total}"
    )

    print(
        f"Passed            : {passed}"
    )

    print(
        f"Failed            : {failed}"
    )

    print(
        f"Success rate      : "
        f"{success_rate:.2f}%"
    )

    print(
        f"Failure rate      : "
        f"{failure_rate:.2f}%"
    )

    print(
        f"Elapsed           : "
        f"{elapsed:.2f} seconds"
    )

    print()
    print("ERROR CATEGORIES")

    if error_categories:

        for category, count in (
            error_categories.most_common()
        ):

            print(
                f"{category:25s} {count}"
            )

    else:

        print("None")

    print()
    print("Results:")
    print(all_results_file)
    print(passed_file)
    print(failed_file)
    print(summary_file)


if __name__ == "__main__":
    main()
