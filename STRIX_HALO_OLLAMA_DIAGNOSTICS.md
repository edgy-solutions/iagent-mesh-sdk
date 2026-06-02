# Strix Halo + Ollama + iagent Diagnostics

Captured 2026-06-01 during sandbox Test 3 (digital twin) debugging.
Symptom: gpt-oss-128k:120b silently falls back to 100% CPU after some
combination of multiple models being loaded, even though the box has
plenty of headroom.

## Hardware / OS / Software baseline

- **Host**: `ai1` (separate from k3s cluster which is at `landinator` 192.168.1.219)
- **iGPU**: AMD Radeon 8060S Graphics, `gfx1151` (Strix Halo)
  - Reported by Ollama: total 114.0 GiB unified memory available
- **RAM**: 128 GB LPDDR5x unified (~121.6 GB system-addressable per ollama)
- **OS**: Ubuntu 24.04 Noble, kernel 6.14.0-1007-oem
- **ROCm installed**: `rocm-core 6.2.0.60200-66~24.04` (June 2024 vintage)
- **ROCm available**: 7.2.4 (`amdgpu-install_7.2.4.70204-1_all.deb` released 2026-05-26)
- **Ollama version**: 0.24.0

## Kernel cmdline (current)

```
BOOT_IMAGE=/boot/vmlinuz-6.14.0-1007-oem
root=UUID=... ro quiet splash
amd_iommu=off
ttm.pages_limit=25165824            # 96 GiB GPU-addressable pool
ttm.page_pool_size=25165824         # 96 GiB
vt.handoff=7
```

96 GiB TTM is enough for any single model but NOT for gpt-oss (70 GB) +
gemma (30 GB) + nomic (~0.6 GB) simultaneously — 100.6 GB total > 96.

## Models in play (iagent workload)

| Model | Size | Used by | Hits ollama via |
|---|---|---|---|
| gpt-oss-128k:120b | 70 GB | Engine O /route_intent, /plan; Engine DA smolagent; Engine E smolagent; cortex-bff orchestration | iagent-config: OLLAMA_BASE_URL, SMOLAGENTS_MODEL |
| gemma4:31b | 30 GB | Mem0 inside Engine A and Engine E | MEM0_OLLAMA_BASE_URL, MEM0_LLM_MODEL |
| nomic-embed-text | 604 MB | Mem0 embeddings (memory storage + recall) | MEM0_OLLAMA_BASE_URL |

## Why "100% CPU" happens — TWO distinct failure modes

### Failure A: TTM eviction race (architectural)

Sequence:
1. Mem0 (inside Engine A or Engine E) initializes on pod startup
2. Mem0 fires nomic embeddings → loads nomic-embed-text to GPU (~0.6 GB)
3. Mem0 fires LLM calls → loads gemma4:31b to GPU (30 GB)
4. Agent reasoner triggers → wants gpt-oss-128k:120b (70 GB)
5. TTM has 96 − 30 − 0.6 = ~65.4 GB free, but gpt-oss needs 70 GB
6. **Ollama sees insufficient GPU memory and silently loads to CPU**
7. KEEP_ALIVE (default 5 min) pins the CPU placement
8. Subsequent calls to gpt-oss stay on CPU until the model unloads

This is what `ollama ps` reveals: `gpt-oss-128k:120b ... 70 GB 100% CPU`.

### Failure B: ROCm gfx1151 stream-sync race (DRIVER BUG — pinned 2026-06-01)

Caught in ollama logs:
```
ROCm error: an illegal memory access was encountered
current device: -1
in function ggml_backend_cuda_synchronize at
/ml/backend/ggml/ggml/src/ggml-cuda/ggml-cuda.cu:94
hipStreamSynchronize(cuda_ctx->stream())
```

Trigger pattern from journalctl:
1. Runner A for gpt-oss is mid-inference
2. Runner B for nomic-embed-text starts (fresh runner per model in ollama)
3. ROCm context switch races → `current device: -1` → corrupt stream
4. `hipStreamSynchronize` calls into a dead stream → illegal memory access
5. **Driver wedges**. Subsequent model loads can't acquire a clean GPU
   context, fall back to CPU.
6. Three `amdgpu_query_gpu_info_init failed` lines confirm the device
   is in a fault state after the crash.

After this crash, Ollama continues serving requests but ALL new loads
go to CPU until the amdgpu driver is reset (reboot or
`modprobe -r amdgpu; modprobe amdgpu` if other handles release).

Failure B happens because Strix Halo / gfx1151 is essentially
unvalidated in ROCm 6.2 (which predates gfx1151's official enablement
in 6.3 and the concurrent-runner stream-sync fixes in 6.4.x). The
fact that single-model inference works at all is somewhat lucky —
6.2's libhsa happens to be compatible enough with gfx1151's ISA.

## What we observed across the session

| Time | State | What was happening |
|---|---|---|
| early | all three models on 100% GPU | clean state, works |
| mid | gpt-oss disappears + gemma stays | TTM eviction (Failure A) |
| mid | gpt-oss reloads on CPU | KEEP_ALIVE pin after failed GPU allocation |
| after illegal access | only nomic remains | Failure B fired; subsequent gpt-oss reloads go CPU |

## Workarounds that fix the iagent flow today

### 1. Disable Mem0 (applied 2026-06-01 to unblock Test 3)

```bash
kubectl -n sandbox patch configmap iagent-config --type merge \
  -p '{"data":{"MEM0_OLLAMA_BASE_URL":"http://localhost:9999"}}'
kubectl -n sandbox rollout restart deployment/iagent-engine-a deployment/iagent-engine-e
```

Engines log `[Mem0Bridge] Skipping memory search` and gracefully
degrade. Removes gemma + nomic from the picture → only gpt-oss on the
GPU → no multi-runner race, no TTM contention.

### 2. Bump TTM pool (only helps Failure A, not B)

`/etc/default/grub` →
`ttm.pages_limit=28835840` and `ttm.page_pool_size=28835840` (= 110 GiB).
Then `sudo update-grub && sudo reboot`.

With 110 GB TTM:
- gpt-oss (70) + gemma (30) + nomic (0.6) = 100.6 GB → fits with ~9 GB margin
- Leaves 18 GB for OS / page cache (was 32 GB before)

WARNING: This alone DOES NOT fix Failure B. You can still hit the
stream-sync race when multiple runners are alive simultaneously.

### 3. Single-runner serialization (workaround for Failure B)

```bash
sudo systemctl edit ollama
```
```ini
[Service]
Environment="OLLAMA_MAX_LOADED_MODELS=1"
Environment="OLLAMA_NUM_PARALLEL=1"
Environment="OLLAMA_SCHED_SPREAD=false"
Environment="HSA_ENABLE_SDMA=0"
Environment="OLLAMA_FLASH_ATTENTION=false"
Environment="OLLAMA_KEEP_ALIVE=24h"
```

- `MAX_LOADED_MODELS=1` — only one model resident at a time, forced
  serialization. Mem0 evicts gpt-oss on each call. Slow but no race.
- `HSA_ENABLE_SDMA=0` — disables the AMD DMA engine, known fix for
  illegal-memory-access during stream sync on older ROCm.
- `OLLAMA_FLASH_ATTENTION=false` — flash attention has GPU-specific
  bugs on RDNA 3.5; disable to be safe.
- `KEEP_ALIVE=24h` — once gpt-oss is loaded, keep it warm for the day.

After editing:
```bash
sudo systemctl restart ollama
```

## The real fix: ROCm 7.2.4

`amdgpu-install_7.2.4.70204-1_all.deb` released 2026-05-26 has:
- Official gfx1151 (Strix Halo) support since 6.4
- Concurrent-runner stream-sync fixes
- Better unified-memory accounting (ROCm-reported "free" matches TTM
  reality, so no false-positive eviction → CPU fallback)

Install path:
```bash
wget https://repo.radeon.com/amdgpu-install/30.30.4/ubuntu/noble/amdgpu-install_7.2.4.70204-1_all.deb
sudo apt install ./amdgpu-install_7.2.4.70204-1_all.deb
sudo apt update
sudo apt install rocm-hip-runtime rocm-smi-lib rocminfo
# Don't add --usecase=dkms if you don't want to touch the kernel module
sudo reboot

# Verify after reboot:
rocminfo | grep -i gfx              # should show gfx1151
apt list --installed 2>/dev/null | grep rocm-core  # should show 7.x
ollama run gpt-oss-128k:120b "hi"   # should land 100% GPU
```

Risk: DKMS rebuild conflicts with the OEM kernel; package conflicts
with the existing 6.2 install. Worth doing as a scheduled maintenance
window, not mid-debug.

After ROCm 7 lands, the workarounds above can be reverted:
- Re-enable Mem0: revert the configmap patch
- Restore TTM to 96 GiB if you bumped it (or leave at 110)
- Drop the `MAX_LOADED_MODELS=1` and other env restrictions

## How to detect each failure mode

```bash
# Live tail ollama for the crash signature:
sudo journalctl -u ollama -f | grep -iE "illegal memory|amdgpu_query|fall.*back|evict"

# Check current model placement:
ollama ps                            # look for "100% CPU" on big model

# Check GPU detection sanity:
rocminfo | grep gfx                  # should print gfx1151
rocm-smi                             # iGPU should show non-zero usage if model loaded to GPU

# Did the driver crash recently?
sudo journalctl -k --since "10 min ago" | grep -iE "amdgpu|drm|gpu"
```

## Why we attribute the crash to ROCm 6.2 + gfx1151 specifically

- ROCm 6.2 release notes do NOT list gfx1151 as a supported target
- ROCm 6.3 added it as experimental
- ROCm 6.4.x added concurrent-context fixes for the
  `ggml_backend_cuda_synchronize` / `hipStreamSynchronize` race path
- The exact crash signature (`current device: -1` during stream
  sync) is the canonical AMD bug 3023 fingerprint that 6.4.x targeted
- Single-runner workloads on 6.2 + gfx1151 are observed working;
  multi-runner workloads (our case) reliably crash within minutes

## Open items / next steps

- [x] ~~Schedule ROCm 7.2.4 upgrade window~~ — done 2026-06-01.
      Upgrade succeeded with `--usecase=rocm --no-dkms`, OEM kernel stayed,
      initial gpt-oss-128k:120b inference hit 35 tok/s on iGPU (vs ~2
      tok/s on CPU).
- [ ] **Failure C (newly discovered)**: Under sustained inference,
      even on ROCm 7.2.4 the gfx1151 GPU wedges. Symptoms:
      1. Inference falls from 100% GPU back to 100% CPU silently
      2. Subsequent model loads hang
      3. `sudo reboot` hangs during shutdown
      4. Only a hard power cycle recovers
      This is the canonical AMD GPU-reset-failure signature. Userspace
      ROCm can't fix it — needs AMD firmware update or vendor-reset
      style kernel workaround. Not yet available for Strix Halo.
- [ ] Decide test path forward (see "Path-forward options" below)
- [ ] Re-enable Mem0 only once Failure C has a fix (or move it to a
      separate GPU host — already in progress on 192.168.1.188)

## Updates from 2026-06-01 session

### ROCm 7.2.4 install recipe (worked)

```bash
# Step 0: Backup
mkdir -p ~/rocm-pre-upgrade-backup
dpkg -l | grep -E "rocm|amdgpu|hsa" > ~/rocm-pre-upgrade-backup/installed-packages.txt
cp /etc/default/grub ~/rocm-pre-upgrade-backup/
ls /etc/apt/sources.list.d/ > ~/rocm-pre-upgrade-backup/apt-sources.txt
for f in /etc/apt/sources.list.d/*rocm* /etc/apt/sources.list.d/*amd*; do
  [ -f "$f" ] && cp "$f" ~/rocm-pre-upgrade-backup/
done

# Step 1: Stop workloads
sudo systemctl stop ollama

# Step 2: Remove old ROCm 6.2 cleanly
sudo apt purge -y $(dpkg -l | grep -E '^ii.*rocm|^ii.*amdgpu-install' | awk '{print $2}')
sudo apt autoremove -y
sudo rm -f /etc/apt/sources.list.d/amdgpu.list /etc/apt/sources.list.d/rocm.list

# Step 3: Install new amdgpu-install (ROCm 7.2.4)
cd /tmp
wget https://repo.radeon.com/amdgpu-install/30.30.4/ubuntu/noble/amdgpu-install_7.2.4.70204-1_all.deb
sudo apt install -y ./amdgpu-install_7.2.4.70204-1_all.deb
sudo apt update

# Step 4: KEY COMMAND — userspace only, NO kernel module
sudo amdgpu-install --usecase=rocm --no-dkms -y
# Run inside tmux! amdgpu-install touches mesa/libdrm and can kill an
# RDP session mid-flight. The install still completes in the background
# but you lose visibility.

# Step 5: Verify before reboot
rocminfo | grep -iE "gfx|Marketing Name"   # should show gfx1151
apt list --installed 2>/dev/null | grep -E "rocm-core|hip-runtime|rocm-smi"
# Expected: rocm-core 7.2.4.70204-93~24.04

# Step 6: Reboot
sudo reboot

# Step 7: Post-reboot verification
uname -r                       # 6.14.0-1007-oem stayed
rocminfo | grep -iE "gfx"      # gfx1151 still detected
sudo systemctl start ollama
ollama run gpt-oss-128k:120b "hi" --verbose
# Expect: 100% GPU, 30+ tok/s
```

### Bug #24 (separate but compounding) — Mem0 embedder URL split

Fixed in invincible-agent commit `afe5fcd`. The Mem0 LLM was reading
`MEM0_OLLAMA_BASE_URL` but the embedder was reading `OLLAMA_BASE_URL`.
Made it impossible to physically split Mem0 onto a separate GPU host.

Now both halves of Mem0 read `MEM0_OLLAMA_BASE_URL` with `OLLAMA_BASE_URL`
as fallback. Setting only `MEM0_OLLAMA_BASE_URL` is now sufficient to
route ALL Mem0 traffic to a sidecar ollama instance.

### Bug Failure C — sustained-load GPU wedge (NEW, blocking)

Discovered after Test 3 (digital twin) attempt #N on ROCm 7.2.4.
Sequence:
1. gpt-oss-128k:120b loaded cleanly to 100% GPU after fresh boot
2. Test 3 fires, agent reasoning runs for several minutes
3. At some point gpt-oss silently drops to 100% CPU
4. From this point: ollama hangs on new model loads
5. `sudo systemctl restart ollama` doesn't recover
6. `sudo reboot` hangs during shutdown (init can't kill processes
   holding GPU memory)
7. ONLY a hard power cycle recovers the box

The fact that **a soft reboot hangs** means the amdgpu kernel module
can't safely release the GPU's allocations during shutdown. The GPU's
memory controller (on Strix Halo, shared with the IOD) is stuck in
a state that the kernel can't reset without a full PCIe re-init,
which only happens on cold boot.

This is **NOT software-fixable from the iagent or ollama side**. It
needs:
- AMD firmware/BIOS update for the AI Max+ 395 platform, OR
- A `vendor-reset`-style kernel patch specific to gfx1151, OR
- Workaround: cap sustained load (use smaller model) so the bug
  never triggers

### Path-forward options for Test 3 specifically

| Option | Pros | Cons |
|---|---|---|
| Use gpt-oss:20b on ai1 for everything | Smaller model = less sustained load on the GPU; might not trigger Failure C | Lower reasoning quality; might fail some agent loops; Test 1/2 already pass with 128k:120b, so this changes the variable mid-validation |
| Move ALL reasoning to .188 GPU (24GB), drop ai1 from the agent path entirely | Sidesteps Strix Halo bugs completely; .188 is stable | 24GB can't hold gpt-oss-128k:120b; have to drop to phi4:14b or qwen-equivalent (avoid Chinese-origin), retest all 3 scenarios |
| Pause Test 3 until AMD firmware fix lands | No more wasted hardware cycles | Indefinite hold — AMD firmware cadence is months not weeks |
| Manually power-cycle ai1 between each Test 3 attempt | Each run gets a clean GPU | Hardware abuse, not scalable, no soak testing possible |

### Workarounds that did NOT help

- `OLLAMA_MAX_LOADED_MODELS=1` — eviction race avoided but Failure C
  still triggers under single-model sustained load
- `HSA_ENABLE_SDMA=0` — didn't change behavior
- `OLLAMA_FLASH_ATTENTION=false` — didn't change behavior
- ROCm 6.2 → 7.2.4 — fixed cold-start case but not the sustained-load
  wedge

### Workarounds that DID help

- ROCm 7.2.4 upgrade — moved from "doesn't even work initially" to
  "works at full speed until Failure C triggers." Real progress.
- Splitting Mem0 onto a separate GPU host (.188) — removes one runner
  from the Strix Halo entirely. Doesn't fix Failure C but reduces
  trigger frequency.
- Power cycle — the only known recovery

## Cross-references

- iagent-mesh-sdk memory: `project_pg18_oauthbearer_wall.md`
  (separate unrelated wall on the Postgres side)
- iagent-mesh-sdk memory: `pingsso-claim-gap.md` (also unrelated, but
  same sandbox testing context)
- iagent-mesh-sdk memory: `conversational-engines-roadmap.md` (broader
  architecture context, not impacted by this GPU issue)
