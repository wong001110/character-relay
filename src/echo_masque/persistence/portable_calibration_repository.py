"""Cross-account ID remapping for portable Calibration Archives."""

from __future__ import annotations

from uuid import uuid4

from echo_masque.calibration import (
    CalibrationArchive,
    CalibrationCaseView,
    CalibrationDatasetView,
    CalibrationImportResult,
)
from echo_masque.persistence.calibration_repository import CalibrationRepository


class PortableCalibrationRepository(CalibrationRepository):
    """Preserve IDs for same-owner backup, remap them for shared imports."""

    def import_archive(
        self,
        owner_id: str,
        archive: CalibrationArchive,
        mode: str,
    ) -> CalibrationImportResult:
        if archive.owner_id == owner_id:
            return super().import_archive(owner_id, archive, mode)

        dataset_ids = {item.id: str(uuid4()) for item in archive.datasets}
        lineage_ids = {
            item.lineage_id: str(uuid4())
            for item in archive.datasets
        }
        remapped: list[CalibrationDatasetView] = []
        for dataset in archive.datasets:
            next_dataset_id = dataset_ids[dataset.id]
            cases = [
                self._remap_case(owner_id, next_dataset_id, item)
                for item in dataset.cases
            ]
            remapped.append(
                dataset.model_copy(
                    update={
                        "id": next_dataset_id,
                        "owner_id": owner_id,
                        "lineage_id": lineage_ids[dataset.lineage_id],
                        "parent_dataset_id": (
                            dataset_ids.get(dataset.parent_dataset_id)
                            if dataset.parent_dataset_id is not None
                            else None
                        ),
                        "cases": cases,
                    }
                )
            )
        portable = archive.model_copy(
            update={"owner_id": owner_id, "datasets": remapped}
        )
        return super().import_archive(owner_id, portable, mode)

    @staticmethod
    def _remap_case(
        owner_id: str,
        dataset_id: str,
        item: CalibrationCaseView,
    ) -> CalibrationCaseView:
        return item.model_copy(
            update={
                "id": str(uuid4()),
                "dataset_id": dataset_id,
                "owner_id": owner_id,
            }
        )
