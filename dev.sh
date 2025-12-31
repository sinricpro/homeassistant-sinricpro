#!/bin/bash
# SinricPro Home Assistant Integration Test Script

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}SinricPro HA Integration Test Environment${NC}"
echo -e "${GREEN}========================================${NC}"

case "${1:-start}" in
    start)
        echo -e "\n${YELLOW}Starting Home Assistant...${NC}"
        docker-compose up -d

        echo -e "\n${YELLOW}Waiting for Home Assistant to start...${NC}"
        sleep 10

        echo -e "\n${GREEN}Home Assistant is starting!${NC}"
        echo -e "Access the UI at: ${GREEN}http://localhost:8123${NC}"
        echo -e "\n${YELLOW}First-time setup:${NC}"
        echo "1. Create an admin account"
        echo "2. Go to Settings > Devices & Services"
        echo "3. Click '+ Add Integration'"
        echo "4. Search for 'SinricPro'"
        echo "5. Enter your SinricPro API key"

        echo -e "\n${YELLOW}View logs:${NC}"
        echo "  docker logs -f homeassistant 2>&1 | grep -i sinricpro"
        ;;

    stop)
        echo -e "\n${YELLOW}Stopping Home Assistant...${NC}"
        docker-compose down
        echo -e "${GREEN}Stopped.${NC}"
        ;;

    restart)
        echo -e "\n${YELLOW}Restarting Home Assistant...${NC}"
        docker-compose restart
        echo -e "${GREEN}Restarted. Wait a few seconds for HA to initialize.${NC}"
        ;;

    logs)
        echo -e "\n${YELLOW}Showing SinricPro logs (Ctrl+C to exit)...${NC}"
        docker logs -f homeassistant 2>&1 | grep -i --color=always sinricpro
        ;;

    logs-all)
        echo -e "\n${YELLOW}Showing all logs (Ctrl+C to exit)...${NC}"
        docker logs -f homeassistant
        ;;

    shell)
        echo -e "\n${YELLOW}Opening shell in container...${NC}"
        docker exec -it homeassistant bash
        ;;

    check)
        echo -e "\n${YELLOW}Checking installation...${NC}"

        echo -e "\n${GREEN}Component files:${NC}"
        docker exec homeassistant ls -la /config/custom_components/sinricpro/ 2>/dev/null || echo -e "${RED}Component not found!${NC}"

        echo -e "\n${GREEN}Manifest:${NC}"
        docker exec homeassistant cat /config/custom_components/sinricpro/manifest.json 2>/dev/null || echo -e "${RED}Manifest not found!${NC}"

        echo -e "\n${GREEN}Recent SinricPro logs:${NC}"
        docker logs homeassistant 2>&1 | grep -i sinricpro | tail -20 || echo "No SinricPro logs found"
        ;;

    clean)
        echo -e "\n${YELLOW}Cleaning up...${NC}"
        docker-compose down -v
        echo -e "${YELLOW}Remove HA config data? (y/N)${NC}"
        read -r response
        if [[ "$response" =~ ^([yY][eE][sS]|[yY])$ ]]; then
            rm -rf ./ha_config/.storage
            rm -rf ./ha_config/home-assistant_v2.db
            echo -e "${GREEN}Config data removed.${NC}"
        fi
        ;;

    *)
        echo "Usage: $0 {start|stop|restart|logs|logs-all|shell|check|clean}"
        echo ""
        echo "Commands:"
        echo "  start     - Start Home Assistant container"
        echo "  stop      - Stop Home Assistant container"
        echo "  restart   - Restart Home Assistant container"
        echo "  logs      - Show SinricPro-related logs"
        echo "  logs-all  - Show all Home Assistant logs"
        echo "  shell     - Open bash shell in container"
        echo "  check     - Check if integration is installed correctly"
        echo "  clean     - Stop and remove container data"
        exit 1
        ;;
esac
