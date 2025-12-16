
import multiprocessing
import time
import signal
import sys
import logging
from pathlib import Path

from src.training.smart_miner_autodistill import run_smart_mining
from src.training.smart_street_miner import run_smart_street_mining
from src.training.mine_grid_for_labels import mine_grid

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - [Orchestrator] - %(levelname)s - %(message)s'
)
logger = logging.getLogger("MiningOrchestrator")

# Fix CUDA Multiprocessing Error
if __name__ == '__main__':
    try:
        multiprocessing.set_start_method('spawn', force=True)
    except RuntimeError:
        pass

# Standalone Worker Functions (Avoids Pickling 'self')
def run_satellite_wrapper():
    try:
        logger.info("Satellite Miner Logic Starting...")
        run_smart_mining()
    except Exception as e:
        logger.error(f"Satellite Miner Crashed: {e}")

def run_fetcher_wrapper():
    try:
        logger.info("Street Fetcher Logic Starting...")
        mine_grid()
    except Exception as e:
        logger.error(f"Street Fetcher Crashed: {e}")
        
def run_street_wrapper():
    try:
        logger.info("Street Smart Miner Logic Starting...")
        run_smart_street_mining()
    except Exception as e:
        logger.error(f"Street Smart Miner Crashed: {e}")

class MiningOrchestrator:
    def __init__(self):
        self.processes = []
        self.running = True
        
        # Handle Signals
        signal.signal(signal.SIGINT, self.shutdown)
        signal.signal(signal.SIGTERM, self.shutdown)

    def start_miners(self):
        logger.info("Initializing Mining Swarm...")
        
        # 1. Satellite Miner (GPU)
        p_sat = multiprocessing.Process(target=run_satellite_wrapper, name="SatelliteMiner")
        p_sat.start()
        self.processes.append(p_sat)
        logger.info(f"🚀 Satellite Miner launched (PID: {p_sat.pid})")
        
        # 2. Street Fetcher (CPU/Network)
        p_fetch = multiprocessing.Process(target=run_fetcher_wrapper, name="StreetFetcher")
        p_fetch.start()
        self.processes.append(p_fetch)
        logger.info(f"🌍 Street Fetcher launched (PID: {p_fetch.pid})")
        
        # 3. Street Smart Miner (GPU)
        time.sleep(5)
        p_street = multiprocessing.Process(target=run_street_wrapper, name="StreetSmartMiner")
        p_street.start()
        self.processes.append(p_street)
        logger.info(f"📸 Street Smart Miner launched (PID: {p_street.pid})")
        
    def monitor(self):
        logger.info("Monitoring active miners...")
        while self.running:
            all_dead = True
            for p in self.processes:
                if p.is_alive():
                    all_dead = False
                else:
                    logger.warning(f"Process {p.name} (PID {p.pid}) has exited.")
                    # Optional: Restart
            
            if all_dead:
                logger.info("All miners have finished.")
                break
                
            time.sleep(5)

    def shutdown(self, signum, frame):
        logger.info("Shutdown signal received! Terminating swarm...")
        self.running = False
        for p in self.processes:
            if p.is_alive():
                logger.info(f"Killing {p.name} ({p.pid})...")
                p.terminate()
                p.join(timeout=2)
                if p.is_alive():
                    p.kill()
        sys.exit(0)

if __name__ == "__main__":
    orch = MiningOrchestrator()
    orch.start_miners()
    orch.monitor()
