flowchart LR
    %% Pipeline Stages
    OR[Opening Range<br/>Stage 1<br/>Reference Level]
    BRK[Breakout<br/>Stage 2<br/>5m Candle]
    RET[Retest<br/>Stage 3<br/>1m Candle]
    IGN[Ignition<br/>Stage 4<br/>Post-Entry]

    %% Level Progression
    L0[Level 0<br/>Candidates<br/>No Trades]
    L1[Level 1<br/>Base Trading<br/>No Filters]
    L2["Level 2<br/>Quality Filter<br/>All Components ≥ C"]
    L3["Level 3<br/>Elite Filter<br/>All ≥ C + Overall ≥ B"]

    %% Flow
    OR --> BRK --> RET
    RET --> IGN
    L0 --> OR
    L1 --> OR
    L2 --> OR
    L3 --> OR

    %% Filtering
    RET --> L2_FILTER{"Level 2 Filter<br/>All Components ≥ C<br/>(Rejects D-grade Components)"}
    IGN --> L3_FILTER{"Level 3 Filter<br/>All Components ≥ C<br/>Overall ≥ 60 pts"}

    L2_FILTER --> L2_ENTRY[Entry<br/>After Filter]
    L3_FILTER --> L3_ENTRY[Entry<br/>After Filter]

    %% Grades
    subgraph "Grading Scale"
        APLUS[A+<br/>4/4 Perfect]
        A[A<br/>3/4 Perfect]
        B[B<br/>2/4 Perfect]
        C["C<br/><2 Perfect<br/>or Has Fails"]
    end

    %% Component Grades
    subgraph "Component Grades"
        GOOD["✅ Good<br/>A/B Grade"]
        WARN["⚠️ Warning<br/>B/C Grade"]
        FAIL["❌ Fail<br/>D Grade"]
    end

    %% Styling
    classDef stageClass fill:#bbdefb,stroke:#1976d2,stroke-width:2px
    classDef levelClass fill:#c8e6c9,stroke:#388e3c,stroke-width:2px
    classDef filterClass fill:#ffcdd2,stroke:#d32f2f,stroke-width:2px
    classDef gradeClass fill:#fff3e0,stroke:#f57c00,stroke-width:2px

    class OR,BRK,RET,IGN stageClass
    class L0,L1,L2,L3 levelClass
    class L2_FILTER,L3_FILTER filterClass
    class APLUS,A,B,C,GOOD,WARN,FAIL gradeClass
