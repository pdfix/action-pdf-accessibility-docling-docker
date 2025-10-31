import logging

from ai import Region
from logger import get_logger

logger: logging.Logger = get_logger()


def bboxes_overlaps(region1: Region, region2: Region) -> bool:
    """
    Check if two regions overlap.

    Args:
        region1 (Region): A region from AI recognition.
        region2 (Region):A region from AI recognition.

    Returns:
        True if regions overlap, False otherwise.
    """
    x_min_1, y_min_1, x_max_1, y_max_1 = region1.box
    x_min_2, y_min_2, x_max_2, y_max_2 = region2.box

    return not (
        x_max_1 < x_min_2  # box1 is left of box2
        or x_min_1 > x_max_2  # box1 is right of box2
        or y_max_1 < y_min_2  # box1 is above box2
        or y_min_1 > y_max_2  # box1 is below box2
    )


class PostProcessingBBoxes:
    """
    Class that takes Docling AI result and compares all region bounding boxes for overlaps
    between them. List of skip ids is created during process
    """

    def __init__(self, results: list[Region]) -> None:
        """
        Initialize the class with Docling AI results.

        Args:
            results (list[Region]): List of all regions on page.
        """
        self.results: list[Region] = results

    def get_list_of_regions(self) -> list[Region]:
        """
        Processes AI recognised regions (with bbox information):
        - group overlaps according to which bounding box (bbox) touches which bbox
        - inside group take bbox with highest score and remove all touching bboxes
        - repeat till all bboxes from group are processed

        Returns:
            List of regions that do not overlap
        """
        overlaps: list[tuple[int, int]] = self._find_overlaps()
        overlapping_bboxes_set: set[int] = self._convert_overlaps_to_set(overlaps)
        groups: list[set[int]] = self._group_overlaps(overlapping_bboxes_set, overlaps)
        removing: set[int] = self._get_removing_indexes(groups, overlaps)
        new_regions: list = []
        for index in range(0, len(self.results)):
            if index in removing:
                continue
            new_regions.append(self.results[index])
        return new_regions

    def _find_overlaps(self) -> list[tuple[int, int]]:
        """
        Create list of tupples which bounding boxes (bboxes) overlaps. Each tupple is unique.

        Returns:
            Unique list of all tupples that overlaps.
        """
        overlaps: list[tuple[int, int]] = []
        number_bboxes = len(self.results)  # Ensure there are boxes to process

        logger.debug("Overlaps:")
        for index1 in range(number_bboxes):
            for index2 in range(index1 + 1, number_bboxes):
                if self._is_overlapping(index1, index2):
                    overlaps.append((index1, index2))
                    # For debugging
                    box1: Region = self.results[index1]
                    box2: Region = self.results[index2]
                    box1_debug_string: str = f"({box1.label} {int(box1.score * 100)}%"
                    box2_debug_string: str = f"({box2.label} {int(box2.score * 100)}%"
                    logger.debug(f"({box1_debug_string}, {box2_debug_string})")

        return overlaps

    def _is_overlapping(self, index1: int, index2: int) -> bool:
        """
        Check if two bounding boxes overlap.

        Args:
            index1 (int): Index of the first bounding box.
            index2 (int): Index of the second bounding box.

        Returns:
            True if the bounding boxes overlap, False otherwise.
        """
        return bboxes_overlaps(self.results[index1], self.results[index2])

    def _bboxes_overlaping_percentages(self, index1: int, index2: int) -> tuple:
        """
        Calculate the overlap percentage between two bounding boxes.

        Args:
            index1 (int): Index of the first bounding box.
            index2 (int): Index of the second bounding box.

        Returns:
            First value is percent (0-100) how much first bounding box has in overlaping area.
            Second value is percent (0-100) how much second bounding box has in overlaping area.
        """
        region1: Region = self.results[index1]
        region2: Region = self.results[index2]

        def bbox_size(region: Region) -> float:
            """
            Calculate the size of a region's bounding box (bbox).

            Args:
                region (Region): A region from AI recognition.

            Returns:
                Size of the bbox.
            """
            x_min, y_min, x_max, y_max = region.box
            return max(0, x_max - x_min) * max(0, y_max - y_min)

        area_1: float = bbox_size(region1)
        area_2: float = bbox_size(region2)

        def bboxes_intersection_size(region_1: Region, region_2: Region) -> float:
            """
            Calculate the intersection size of two region's bounding boxes.

            Args:
                region_1 (Region): A region from AI recognition.
                region_2 (Region): A region from AI recognition.

            Returns:
                Size of intersection.
            """
            x_min_1, y_min_1, x_max_1, y_max_1 = region_1.box
            x_min_2, y_min_2, x_max_2, y_max_2 = region_2.box

            x_overlap: float = max(0, min(x_max_1, x_max_2) - max(x_min_1, x_min_2))
            y_overlap: float = max(0, min(y_max_1, y_max_2) - max(y_min_1, y_min_2))

            return x_overlap * y_overlap

        intersect_area: float = bboxes_intersection_size(region1, region2)

        percent1: float = (intersect_area / area_1) * 100 if area_1 > 0 else 0
        percent2: float = (intersect_area / area_2) * 100 if area_2 > 0 else 0

        return percent1, percent2

    def _convert_overlaps_to_set(self, overlaps: list[tuple[int, int]]) -> set[int]:
        """
        From list of tupples create set of index.

        Args:
            overlaps (list[tuple[int, int]]): Unique list of all tupples that overlaps.

        Return:
            Set of bbox indexes that overlaps with some other bbox.
        """
        return {i for pair in overlaps for i in pair}

    def _get_group_index(self, searching: int, all_groups: list[set[int]]) -> int:
        """
        Find index of group that contain searching element.

        Args:
            searching (int): Index of bbox we are searching for.
            all_groups (list[set[int]]): Currently built groups that contain set of indexes.

        Returns:
            Index if found, -1 otherwise.
        """
        return next((i for i, group in enumerate(all_groups) if searching in group), -1)

    def _group_overlaps(self, overlapping_bboxes_set: set[int], overlaps: list[tuple[int, int]]) -> list[set[int]]:
        """
        Create disjointed groups that contain indexes of bboxes that touches themselves directly or through multiple
        bboxes.

        Args:
            overlapping_bboxes_set (set[int]): Set of bbox indexes that overlaps with some other bbox.
            overlaps (list[tuple[int, int]]): Unique list of all tupples that overlaps.

        Returns:
            List of groups, where each group contain set of bbox indexes that overlaps either directly or through some
            other bbox(es).
        """
        groups: list[set[int]] = []
        for box_index in overlapping_bboxes_set:
            # Find group if exists or create new
            group_index: int = self._get_group_index(box_index, groups)
            group: set[int] = groups[group_index] if group_index >= 0 else set()

            # Fill touching members into group that are not already there:
            for index1, index2 in overlaps:
                if box_index == index1:
                    group.add(index2)
                if box_index == index2:
                    group.add(index1)

            # Save group
            if group_index < 0:
                groups.append(group)
            else:
                groups[group_index] = group

        # Merge groups that have any member in intersection
        remove_group_indexes: list[int] = []
        unique_groups: list[set[int]] = []
        for group_index1 in range(len(groups)):
            if group_index1 in remove_group_indexes:
                continue
            group1: set[int] = groups[group_index1]
            for group_index2 in range(group_index1 + 1, len(groups)):
                if group_index2 in remove_group_indexes:
                    continue
                group2: set[int] = groups[group_index2]
                if group1.intersection(group2):
                    group1 = group1.union(group2)
                    remove_group_indexes.append(group_index2)
            unique_groups.append(group1)

        # For debugging
        logger.debug("Found groups:")
        for group in groups:
            logger.debug("Group:")
            for member_index in group:
                region: Region = self.results[member_index]
                logger.debug(f"{region.label} {round(region.score * 100)}%    {region.box}")

        # Return disjoint sets
        return unique_groups

    def _indexes_that_can_be_merged(self, groups: list[set[int]]) -> tuple[int, int]:
        """
        Find if any two groups can be merged together.

        Args:
            groups (list[set[int]]): List of groups.

        Returns:
            If 2 groups can be merged return their indexes, otherwise return -1, -1
        """
        groups_size: int = len(groups)
        for index1 in range(groups_size):
            group1: set[int] = groups[index1]
            for index2 in range(index1 + 1, groups_size):
                group2: set[int] = groups[index2]
                if group1 & group2:
                    return index1, index2
        return -1, -1

    def _get_removing_indexes(self, groups: list[set[int]], overlaps: list[tuple[int, int]]) -> set[int]:
        """
        Process each group and gather removing indexes from each group.

        Args:
            groups (list[set[int]]): List of groups, where each group contains set of bbox indexes that overlaps either
                directly or through some other bbox(es).
            overlaps (list[tuple[int, int]]): Unique list of all tupples that overlaps.

        Returns:
            Set of indexes that should be removed.
        """
        remove_indexes: set[int] = set()

        for group in groups:
            removed: set[int] = self._process_group(group, overlaps)
            remove_indexes = remove_indexes.union(removed)
            # For debugging
            logger.debug("Removing:")
            for index in removed:
                region: Region = self.results[index]
                logger.debug(f"{region.label} {round(region.score * 100)}%")

        # For debugging
        logger.debug("All Removing:")
        for index in remove_indexes:
            region = self.results[index]
            logger.debug(f"{region.label} {round(region.score * 100)}%")

        return remove_indexes

    def _process_group(self, group: set[int], overlaps: list[tuple[int, int]]) -> set[int]:
        """
        Process members of group:
        - take highest score members
        - remove all its direct neighbours
        - repeat till all members are processed

        Args:
            group (set[int]): Group containing set of bbox indexes that overlaps either directly
                or through some other bbox(es).
            overlaps (list[tuple[int, int]]): Unique list of all tupples that overlaps.

        Returns:
            Set of indexes that should be removed.
        """
        removed: set[int] = set()
        while group:
            # Find highest score
            max_score: int = max(group, key=lambda x: float(self.results[x].score))

            to_further_process: set[int] = set()
            for member in group:
                if member == max_score:
                    # We are using higher score
                    pass
                elif self._is_direct_neightbour(max_score, member, overlaps):
                    # Remove direct neighbours
                    removed.add(member)
                else:
                    # Rest keep for next processing round
                    to_further_process.add(member)
            group = to_further_process

        return removed

    def _is_direct_neightbour(self, max_score_index: int, member_index: int, overlaps: list[tuple[int, int]]) -> bool:
        """
        Check if two members overlap directly.

        Args:
            max_score_index (int): Member of group that has highest score.
            member_index (int): Member we want to check if it is neighbour.
            overlaps (list[tuple[int, int]]): Unique list of all tupples that overlaps.

        Returns:
            True if bboxes overlaps.
        """
        for index1, index2 in overlaps:
            if index1 == max_score_index and index2 == member_index:
                return True
            if index1 == member_index and index2 == max_score_index:
                return True
        return False
