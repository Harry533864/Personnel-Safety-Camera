#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence


def parse_shape(value: str) -> tuple[int, ...]:
    parts = value.lower().replace(",", "x").split("x")
    try:
        shape = tuple(int(part) for part in parts if part.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"invalid shape: {value}") from exc
    if not shape or any(dim <= 0 for dim in shape):
        raise argparse.ArgumentTypeError(f"invalid shape: {value}")
    return shape


def concrete_shape(shape: Sequence[int], fallback: tuple[int, ...]) -> tuple[int, ...]:
    if len(shape) == len(fallback):
        return tuple(fallback[index] if int(dim) <= 0 else int(dim) for index, dim in enumerate(shape))
    return tuple(1 if int(dim) <= 0 else int(dim) for dim in shape)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a TensorRT engine from an ONNX model.")
    parser.add_argument("--onnx", required=True, type=Path)
    parser.add_argument("--engine", required=True, type=Path)
    parser.add_argument("--fp16", action="store_true")
    parser.add_argument("--workspace-mb", type=int, default=2048)
    parser.add_argument("--input-shape", type=parse_shape, default=(1, 3, 640, 640))
    args = parser.parse_args()

    import tensorrt as trt

    if not args.onnx.is_file():
        raise FileNotFoundError(args.onnx)

    logger = trt.Logger(trt.Logger.INFO)
    builder = trt.Builder(logger)
    flag = 1 << int(trt.NetworkDefinitionCreationFlag.EXPLICIT_BATCH)
    network = builder.create_network(flag)
    parser_obj = trt.OnnxParser(network, logger)

    if not parser_obj.parse(args.onnx.read_bytes()):
        errors = [str(parser_obj.get_error(index)) for index in range(parser_obj.num_errors)]
        raise RuntimeError("ONNX parse failed:\n" + "\n".join(errors))

    config = builder.create_builder_config()
    workspace_bytes = int(args.workspace_mb) * 1024 * 1024
    if hasattr(config, "set_memory_pool_limit"):
        config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, workspace_bytes)
    else:
        config.max_workspace_size = workspace_bytes

    if args.fp16:
        if builder.platform_has_fast_fp16:
            config.set_flag(trt.BuilderFlag.FP16)
        else:
            print("warning: platform_has_fast_fp16 is false; building without FP16 flag")

    needs_profile = False
    for index in range(network.num_inputs):
        shape = tuple(int(dim) for dim in network.get_input(index).shape)
        if any(dim <= 0 for dim in shape):
            needs_profile = True
            break

    if needs_profile:
        profile = builder.create_optimization_profile()
        for index in range(network.num_inputs):
            tensor = network.get_input(index)
            shape = concrete_shape(tuple(int(dim) for dim in tensor.shape), args.input_shape)
            profile.set_shape(tensor.name, shape, shape, shape)
        config.add_optimization_profile(profile)

    args.engine.parent.mkdir(parents=True, exist_ok=True)
    serialized = None
    if hasattr(builder, "build_serialized_network"):
        serialized = builder.build_serialized_network(network, config)
    else:
        engine = builder.build_engine(network, config)
        serialized = engine.serialize() if engine is not None else None

    if serialized is None:
        raise RuntimeError("TensorRT engine build failed")

    args.engine.write_bytes(bytes(serialized))
    print(f"TensorRT engine written: {args.engine}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
