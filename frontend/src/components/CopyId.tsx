import { useState } from "react";
import { useTranslation } from "react-i18next";
import styles from "./CopyId.module.css";

/** Opaque ids stay off the canvas; this hands one over only when asked for. */
export function CopyId({ label, value }: { label: string; value: string }) {
  const { t } = useTranslation();
  const [done, setDone] = useState(false);
  return (
    <button
      type="button"
      className={styles.copy}
      title={value}
      data-done={done ? "true" : "false"}
      onClick={() => {
        void navigator.clipboard
          ?.writeText(value)
          .then(() => {
            setDone(true);
            setTimeout(() => setDone(false), 1500);
          })
          .catch(() => {});
      }}
    >
      {done ? t("common.copied") : label}
    </button>
  );
}
