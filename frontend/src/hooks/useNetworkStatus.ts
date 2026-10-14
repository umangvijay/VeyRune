"use client";
import { useState, useEffect } from "react";
import { throttle } from "radash";

interface NetworkInformation extends EventTarget {
  effectiveType?: string;
  saveData?: boolean;
}

type NavigatorWithNetwork = Navigator & {
  connection?: NetworkInformation;
  mozConnection?: NetworkInformation;
  webkitConnection?: NetworkInformation;
};

export function useNetworkStatus() {
  const [isLowEnd, setIsLowEnd] = useState(false);

  useEffect(() => {
    // Throttle the check so it doesn't run continuously and save main thread time on low-end devices
    const checkNetwork = throttle({ interval: 2000 }, () => {
      const networkNavigator = navigator as NavigatorWithNetwork;
      const connection = networkNavigator.connection || networkNavigator.mozConnection || networkNavigator.webkitConnection;
      
      if (connection) {
        const isSaveData = connection.saveData === true;
        const isSlow = ["slow-2g", "2g", "3g"].includes(connection.effectiveType);
        
        if (isSaveData || isSlow) {
          setIsLowEnd(true);
          // Add global class to disable heavy CSS animations (mesh gradients, blurs, etc)
          document.documentElement.classList.add("reduce-data");
        } else {
          setIsLowEnd(false);
          document.documentElement.classList.remove("reduce-data");
        }
      }
    });

    checkNetwork();
    
    const networkNavigator = navigator as NavigatorWithNetwork;
    const connection = networkNavigator.connection || networkNavigator.mozConnection || networkNavigator.webkitConnection;
    if (connection) {
      connection.addEventListener("change", checkNetwork);
      return () => connection.removeEventListener("change", checkNetwork);
    }
  }, []);

  return { isLowEnd };
}
