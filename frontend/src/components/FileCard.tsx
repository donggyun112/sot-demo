import { useTranslation } from "react-i18next";
import { fileKind } from "./attachedFile";
import styles from "./FileCard.module.css";

/**
 * A file, as a card. Used in two places for one reason: what is staged in the
 * composer and what ends up in the transcript are the same object, so they
 * had better look like it.
 */
export function FileCard({
  name,
  lines,
  onRemove,
}: {
  name: string;
  lines?: number;
  /** Present only while it is still a draft nobody has sent. */
  onRemove?: () => void;
}) {
  const { t } = useTranslation();
  const kind = fileKind(name);
  return (
    <div className={styles.card}>
      <div className={styles.name} title={name}>
        {name}
      </div>
      {lines !== undefined && (
        <div className={styles.meta}>{t("agent.fileLines", { count: lines })}</div>
      )}
      {kind && <span className={styles.kind}>{kind}</span>}
      {onRemove && (
        <button
          aria-label={t("agent.fileRemove", { name })}
          className={styles.remove}
          onClick={onRemove}
          type="button"
        >
          ×
        </button>
      )}
    </div>
  );
}
