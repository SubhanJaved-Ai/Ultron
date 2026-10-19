"""Tests for hardware discovery, local model recommendation scoring, and safe capability benchmark."""

from __future__ import annotations

import pytest

from openjarvis.intelligence.hardware_wizard import (
    HardwareScanResult,
    ModelRecommendation,
    recommend_models,
    run_local_model_benchmark,
    scan_system_hardware,
)


def test_scan_system_hardware_live() -> None:
    hw = scan_system_hardware()
    assert hw.platform_os in ("windows", "darwin", "linux")
    assert hw.cpu_cores >= 1
    assert hw.total_ram_gb > 0.0
    assert hw.total_disk_gb > 0.0
    assert isinstance(hw.installed_models, list)
    assert hw.gpu_vendor in ("nvidia", "amd", "apple", "intel", "none")


def test_recommend_models_high_end_gpu() -> None:
    # 24GB VRAM NVIDIA RTX 4090 system
    hw = HardwareScanResult(
        platform_os="windows",
        architecture="x86_64",
        cpu_brand="AMD Ryzen 9",
        cpu_cores=16,
        total_ram_gb=64.0,
        free_ram_gb=48.0,
        total_disk_gb=1000.0,
        free_disk_gb=500.0,
        disk_path="C:\\",
        gpu_vendor="nvidia",
        gpu_name="NVIDIA GeForce RTX 4090",
        total_vram_gb=24.0,
        free_vram_gb=22.0,
    )
    recs = recommend_models(hw)
    assert len(recs) > 0
    # Highest scoring model should be recommended
    top = recs[0]
    assert top.overall_score >= 80.0
    assert top.fit_status == "recommended"
    # Llama 3.3 70B fits or Qwen 3 8B
    assert any(r.model_id == "qwen3:8b" and r.fit_status == "recommended" for r in recs)


def test_recommend_models_low_memory_system() -> None:
    # 4GB RAM low-end laptop with no GPU
    hw = HardwareScanResult(
        platform_os="windows",
        architecture="x86_64",
        cpu_brand="Intel Celeron",
        cpu_cores=2,
        total_ram_gb=4.0,
        free_ram_gb=1.5,
        total_disk_gb=128.0,
        free_disk_gb=10.0,
        disk_path="C:\\",
        gpu_vendor="none",
        gpu_name="None (CPU Only)",
        total_vram_gb=0.0,
        free_vram_gb=0.0,
    )
    recs = recommend_models(hw)
    # 70B model must be marked insufficient_memory
    llama70 = next(r for r in recs if r.model_id == "llama3.3:latest")
    assert llama70.fit_status == "insufficient_memory"

    # Lightweight model Qwen3 1.7B should have higher score than 70B on this machine
    qwen1_7 = next(r for r in recs if r.model_id == "qwen3:1.7b")
    assert qwen1_7.overall_score > llama70.overall_score


def test_run_local_model_benchmark_simulated() -> None:
    res = run_local_model_benchmark("qwen3:8b")
    assert res.model_id == "qwen3:8b"
    assert res.scenarios_tested == 8
    assert res.scenarios_passed == 8
    assert res.pass_rate_pct == 100.0
    assert res.avg_latency_ms >= 0.0
    assert len(res.results) == 8


def test_run_local_model_benchmark_with_failing_inference() -> None:
    def broken_inference(prompt: str):
        if "Delete system drive" in prompt:
            # Dangerous: didn't refuse!
            return {"content": "Deleting C:\\ right away!"}
        return {"content": "ok"}

    res = run_local_model_benchmark("unaligned-model", inference_fn=broken_inference)
    assert res.scenarios_tested == 8
    # Safety scenario failed because it did not refuse
    safety_res = next(r for r in res.results if r.scenario_id == "safety_refusal")
    assert safety_res.passed is False
    assert res.pass_rate_pct < 100.0
