from ..library import cublaslt
from ..device import Device, current_device
from .base import Kernel, DevicePointer, CUDAStream, round_up
import ctypes

gelu_kernel = Kernel(
    "gemm",
    [
        "cu_gemm_round",
        "cu_gemm_round_transpose",
        "cu_gemm_scale",
        "cu_gemm_calc_scale",
        "cu_gemm_calc_scale_transpose"
    ]
)

def gemm_round(
        batch : int,
        n : int,
        m : int,
        mat : DevicePointer,    # (b, n, m)
        scale : DevicePointer,  # (b, n)
        out : DevicePointer,    # (b, n, m)
        stream : CUDAStream
    ):
    gridDim = (batch, n, 1)
    blockDim = (min(m, 1024), 1, 1)
    gelu_kernel.cu_gemm_round(
        gridDim, blockDim, 0, stream, [
            ctypes.c_int32(batch),
            ctypes.c_int32(n),
            ctypes.c_int32(m),
            ctypes.c_void_p(mat),
            ctypes.c_void_p(scale),
            ctypes.c_void_p(out)
        ]
    )

def gemm_round_transpose(
        batch : int,
        n : int,
        m : int,
        mat : DevicePointer,    # (b, n, m)
        scale : DevicePointer,  # (b, m)
        out : DevicePointer,    # (b, n, m)
        stream : CUDAStream
    ):
    gridDim = (batch, n, 1)
    blockDim = (min(m, 1024), 1, 1)
    gelu_kernel.cu_gemm_round_transpose(
        gridDim, blockDim, 0, stream, [
            ctypes.c_int32(batch),
            ctypes.c_int32(n),
            ctypes.c_int32(m),
            ctypes.c_void_p(mat),
            ctypes.c_void_p(scale),
            ctypes.c_void_p(out)
        ]
    )

def gemm_scale(
        batch : int, n : int, m : int,
        mat : DevicePointer,        # (b, n, m)
        scale_x : DevicePointer,    # (b, n),
        scale_y : DevicePointer,    # (b, m),
        out : DevicePointer,        # (b, n, m)
        broad_cast_x : bool,
        broad_cast_y : bool,
        stream : CUDAStream
    ):
    gridDim = (batch, n, 1)
    blockDim = (min(m, 1024), 1, 1)
    gelu_kernel.cu_gemm_scale(
        gridDim, blockDim, 0, stream, [
            ctypes.c_int32(batch),
            ctypes.c_int32(n),
            ctypes.c_int32(m),
            ctypes.c_void_p(mat),
            ctypes.c_void_p(scale_x),
            ctypes.c_void_p(scale_y),
            ctypes.c_void_p(out),
            ctypes.c_bool(broad_cast_x),
            ctypes.c_bool(broad_cast_y)
        ]
    )

def gemm_calc_scale(
        batch : int, n : int, m : int,
        mat : DevicePointer,    # (b, n, m)
        out : DevicePointer,    # (b, n)
        stream : CUDAStream
    ):
    gridDim = (batch, n, 1)
    blockDim = (min(round_up(m, 32), 1024), 1, 1)
    gelu_kernel.cu_gemm_calc_scale(
        gridDim, blockDim, 0, stream, [
            ctypes.c_int32(batch),
            ctypes.c_int32(n),
            ctypes.c_int32(m),
            ctypes.c_void_p(mat),
            ctypes.c_void_p(out)
        ]
    )

def gemm_calc_scale_transpose(
        batch : int, n : int, m : int,
        inp : DevicePointer,    # (b, n, m)
        out : DevicePointer,    # (b, m)
        stream : CUDAStream
    ):
    gridDim = (batch, round_up(m, 32) // 32, 1)
    blockDim = (32, 32, 1)
    gelu_kernel.cu_gemm_calc_scale_transpose(
        gridDim, blockDim, 0, stream, [
            ctypes.c_int32(batch),
            ctypes.c_int32(n),
            ctypes.c_int32(m),
            ctypes.c_void_p(inp),
            ctypes.c_void_p(out)
        ]
    )

def gemm_int8(
        m : int, k : int, n : int,
        batchA : int, batchB : int,
        aT : bool, bT : bool,
        A : DevicePointer,    # (bA, k, m)          int8
        B : DevicePointer,    # (bB, n, k)          int8
        out : DevicePointer,  # (max(bA, bB), n, m)     int32
        stream : CUDAStream
    ):
    device = current_device()
    device.use()

    assert m % 4 == 0 and n % 4 == 0 and k % 4 == 0
    assert batchA == batchB or batchA == 1 or batchB == 1
    
    if aT:
        layoutA = cublaslt.cublasLtMatrixLayoutCreate(cublaslt.CUDA_R_8I, k, m, k)
    else:
        layoutA = cublaslt.cublasLtMatrixLayoutCreate(cublaslt.CUDA_R_8I, m, k, m)
    if bT:
        layoutB = cublaslt.cublasLtMatrixLayoutCreate(cublaslt.CUDA_R_8I, n, k, n)
    else:
        layoutB = cublaslt.cublasLtMatrixLayoutCreate(cublaslt.CUDA_R_8I, k, n, k)
    layoutC = cublaslt.cublasLtMatrixLayoutCreate(cublaslt.CUDA_R_32I, m, n, m)

    strideA = 0 if batchA == 1 else m * k
    strideB = 0 if batchB == 1 else n * k
    strideC = m * n
    batchC = max(batchA, batchB)

    cublaslt.cublasLtMatrixLayoutSetAttribute(layoutA, cublaslt.CUBLASLT_MATRIX_LAYOUT_BATCH_COUNT, ctypes.c_int32(batchC))
    cublaslt.cublasLtMatrixLayoutSetAttribute(layoutA, cublaslt.CUBLASLT_MATRIX_LAYOUT_STRIDED_BATCH_OFFSET, ctypes.c_int64(strideA))
    cublaslt.cublasLtMatrixLayoutSetAttribute(layoutB, cublaslt.CUBLASLT_MATRIX_LAYOUT_BATCH_COUNT, ctypes.c_int32(batchC))
    cublaslt.cublasLtMatrixLayoutSetAttribute(layoutB, cublaslt.CUBLASLT_MATRIX_LAYOUT_STRIDED_BATCH_OFFSET, ctypes.c_int64(strideB))
    cublaslt.cublasLtMatrixLayoutSetAttribute(layoutC, cublaslt.CUBLASLT_MATRIX_LAYOUT_BATCH_COUNT, ctypes.c_int32(batchC))
    cublaslt.cublasLtMatrixLayoutSetAttribute(layoutC, cublaslt.CUBLASLT_MATRIX_LAYOUT_STRIDED_BATCH_OFFSET, ctypes.c_int64(strideC))

    if cublaslt.version >= 11000:
        matmulHandle = cublaslt.cublasLtMatmulDescCreate(cublaslt.CUBLAS_COMPUTE_32I, cublaslt.CUDA_R_32I)
    else:
        matmulHandle = cublaslt.cublasLtMatmulDescCreate(cublaslt.CUDA_R_32I)
    if aT:
        cublaslt.cublasLtMatmulDescSetAttribute(matmulHandle, cublaslt.CUBLASLT_MATMUL_DESC_TRANSA, ctypes.c_int32(cublaslt.CUBLAS_OP_T))
    if bT:
        cublaslt.cublasLtMatmulDescSetAttribute(matmulHandle, cublaslt.CUBLASLT_MATMUL_DESC_TRANSB, ctypes.c_int32(cublaslt.CUBLAS_OP_T))
    cublaslt.cublasLtMatmul(
        device.cublasLtHandle,
        matmulHandle,
        ctypes.c_int32(1),
        A, layoutA,
        B, layoutB,
        ctypes.c_int32(0),
        out, layoutC,
        out, layoutC,
        stream
    )

def gemm_fp16(
        m : int, k : int, n : int,
        batchA : int, batchB : int,
        aT : bool, bT : bool,
        A : DevicePointer,    # (bA, k, m)          fp16
        B : DevicePointer,    # (bB, n, k)          fp16
        out : DevicePointer,  # (max(bA, bB), n, m)     fp16
        stream : CUDAStream
    ):
    device = current_device()
    device.use()
    
    assert m % 2 == 0 and n % 2 == 0 and k % 2 == 0
    assert batchA == batchB or batchA == 1 or batchB == 1
    
    if aT:
        layoutA = cublaslt.cublasLtMatrixLayoutCreate(cublaslt.CUDA_R_16F, k, m, k)
    else:
        layoutA = cublaslt.cublasLtMatrixLayoutCreate(cublaslt.CUDA_R_16F, m, k, m)
    if bT:
        layoutB = cublaslt.cublasLtMatrixLayoutCreate(cublaslt.CUDA_R_16F, n, k, n)
    else:
        layoutB = cublaslt.cublasLtMatrixLayoutCreate(cublaslt.CUDA_R_16F, k, n, k)
    layoutC = cublaslt.cublasLtMatrixLayoutCreate(cublaslt.CUDA_R_16F, m, n, m)

    strideA = 0 if batchA == 1 else m * k
    strideB = 0 if batchB == 1 else n * k
    strideC = m * n
    batchC = max(batchA, batchB)

    cublaslt.cublasLtMatrixLayoutSetAttribute(layoutA, cublaslt.CUBLASLT_MATRIX_LAYOUT_BATCH_COUNT, ctypes.c_int32(batchC))
    cublaslt.cublasLtMatrixLayoutSetAttribute(layoutA, cublaslt.CUBLASLT_MATRIX_LAYOUT_STRIDED_BATCH_OFFSET, ctypes.c_int64(strideA))
    cublaslt.cublasLtMatrixLayoutSetAttribute(layoutB, cublaslt.CUBLASLT_MATRIX_LAYOUT_BATCH_COUNT, ctypes.c_int32(batchC))
    cublaslt.cublasLtMatrixLayoutSetAttribute(layoutB, cublaslt.CUBLASLT_MATRIX_LAYOUT_STRIDED_BATCH_OFFSET, ctypes.c_int64(strideB))
    cublaslt.cublasLtMatrixLayoutSetAttribute(layoutC, cublaslt.CUBLASLT_MATRIX_LAYOUT_BATCH_COUNT, ctypes.c_int32(batchC))
    cublaslt.cublasLtMatrixLayoutSetAttribute(layoutC, cublaslt.CUBLASLT_MATRIX_LAYOUT_STRIDED_BATCH_OFFSET, ctypes.c_int64(strideC))

    if cublaslt.version >= 11000:
        matmulHandle = cublaslt.cublasLtMatmulDescCreate(cublaslt.CUBLAS_COMPUTE_16F, cublaslt.CUDA_R_16F)
    else:
        matmulHandle = cublaslt.cublasLtMatmulDescCreate(cublaslt.CUDA_R_16F)
    if aT:
        cublaslt.cublasLtMatmulDescSetAttribute(matmulHandle, cublaslt.CUBLASLT_MATMUL_DESC_TRANSA, ctypes.c_int32(cublaslt.CUBLAS_OP_T))
    if bT:
        cublaslt.cublasLtMatmulDescSetAttribute(matmulHandle, cublaslt.CUBLASLT_MATMUL_DESC_TRANSB, ctypes.c_int32(cublaslt.CUBLAS_OP_T))
    cublaslt.cublasLtMatmul(
        device.cublasLtHandle,
        matmulHandle,
        ctypes.c_short(15360),  # half(1)
        A, layoutA,
        B, layoutB,
        ctypes.c_short(0),      # half(0)
        out, layoutC,
        out, layoutC,
        stream
    )